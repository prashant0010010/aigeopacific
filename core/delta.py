"""
core/delta.py
-------------
Metric delta comparison between two AuditResult objects for AiGeoPacific.

When a user re-audits a URL they have audited before, this module computes
the change in CQS and per-metric scores between the older and newer run.
The resulting AuditDelta is stored on AuditResult.delta and rendered in
both the Streamlit UI and the PDF "Progress Since Last Audit" section.

Design decisions:
- Both audits must be for the same normalised URL. Mismatched URLs return None.
- "Unchanged" means the delta is within ±1.0 point (float noise tolerance).
- AuditDelta is fully serialisable — it is stored inside the AuditResult JSON.
- This module has zero Streamlit or PDF imports. Pure data logic only.

Imported by:
  - core/audit_runner.py: compute_delta() called after save if prior audit found
  - ui/history_view.py: delta display in compare view
  - reports/pdf_builder.py: "Progress Since Last Audit" section
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from core.models import AuditDelta, AuditResult

logger = logging.getLogger(__name__)

# Scores within this band are considered "unchanged" (not noise-sensitive)
_UNCHANGED_THRESHOLD = 1.0


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _normalise_url(url: str) -> str:
    """
    Normalise a URL to a canonical form for comparison.

    Strips scheme (http/https), www prefix, trailing slashes,
    and lowercases the result.

    Args:
        url: Raw URL string.

    Returns:
        Normalised string, e.g. "ahrefs.com/blog/seo-tips"
    """
    normalised = url.lower().strip()
    normalised = re.sub(r'^https?://', '', normalised)
    normalised = re.sub(r'^www\.', '', normalised)
    normalised = normalised.rstrip('/')
    return normalised


def _describe_delta(cqs_a: float, cqs_b: float) -> str:
    """
    Generate a plain-English summary of the CQS change.

    Args:
        cqs_a: CQS from the older audit.
        cqs_b: CQS from the newer audit.

    Returns:
        Human-readable string, e.g. "CQS improved from 43 to 61 (+18 points)"
    """
    delta = cqs_b - cqs_a
    direction = "improved" if delta > 0 else ("declined" if delta < 0 else "unchanged")
    sign = "+" if delta > 0 else ""

    if abs(delta) < _UNCHANGED_THRESHOLD:
        return f"CQS remained steady at {cqs_b:.0f} (no significant change)"

    return (
        f"CQS {direction} from {cqs_a:.0f} to {cqs_b:.0f} "
        f"({sign}{delta:.0f} points)"
    )


def _extract_metric_scores(result: AuditResult) -> dict[str, float]:
    """
    Extract a flat dict of metric_name -> score from an AuditResult.

    Handles an empty or missing metrics list gracefully by returning {}.

    Args:
        result: AuditResult object with populated metrics list.

    Returns:
        Dict mapping metric name to numeric score (0–100).
    """
    if not result.metrics:
        return {}

    return {m.name: float(m.score) for m in result.metrics}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def compute_delta(older: AuditResult, newer: AuditResult) -> Optional[AuditDelta]:
    """
    Compute the change in CQS and per-metric scores between two audits.

    Both audits must be for the same URL (after normalisation). If they
    differ, this function logs a warning and returns None — it will never
    silently compare mismatched URLs.

    The returned AuditDelta classifies each metric as:
      - improved:   score increased by more than _UNCHANGED_THRESHOLD
      - regressed:  score decreased by more than _UNCHANGED_THRESHOLD
      - unchanged:  delta within ±_UNCHANGED_THRESHOLD

    Args:
        older: The earlier AuditResult (lower timestamp).
        newer: The later AuditResult (higher timestamp). This is the "current" run.

    Returns:
        AuditDelta if URLs match and computation succeeds, else None.
    """
    # -- URL match guard --
    older_url = _normalise_url(older.url)
    newer_url = _normalise_url(newer.url)

    if older_url != newer_url:
        logger.warning(
            "compute_delta called with mismatched URLs: '%s' vs '%s'. "
            "Returning None.",
            older.url, newer.url
        )
        return None

    # -- Timestamp ordering guard --
    # If timestamps are missing, use epoch-zero so the function still runs
    ts_a: datetime = older.timestamp or datetime(2000, 1, 1, tzinfo=timezone.utc)
    ts_b: datetime = newer.timestamp or datetime(2000, 1, 2, tzinfo=timezone.utc)

    if ts_a > ts_b:
        logger.warning(
            "compute_delta: 'older' audit (%s) has a later timestamp than "
            "'newer' audit (%s). Arguments may be swapped.",
            ts_a.isoformat(), ts_b.isoformat()
        )
        # Swap so delta direction is always older -> newer
        older, newer = newer, older
        ts_a, ts_b = ts_b, ts_a

    # -- CQS delta --
    cqs_a = float(older.cqs or 0.0)
    cqs_b = float(newer.cqs or 0.0)
    cqs_delta = round(cqs_b - cqs_a, 2)

    # -- Per-metric deltas --
    scores_a = _extract_metric_scores(older)
    scores_b = _extract_metric_scores(newer)

    # Union of all metric names present in either audit
    all_metrics = set(scores_a.keys()) | set(scores_b.keys())

    metric_deltas: dict[str, float] = {}
    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []

    for metric_name in sorted(all_metrics):
        score_a = scores_a.get(metric_name, 0.0)
        score_b = scores_b.get(metric_name, 0.0)
        delta_val = round(score_b - score_a, 2)
        metric_deltas[metric_name] = delta_val

        if delta_val > _UNCHANGED_THRESHOLD:
            improved.append(metric_name)
        elif delta_val < -_UNCHANGED_THRESHOLD:
            regressed.append(metric_name)
        else:
            unchanged.append(metric_name)

    summary = _describe_delta(cqs_a, cqs_b)

    try:
        result = AuditDelta(
            url=newer.url,
            audit_a_timestamp=ts_a,
            audit_b_timestamp=ts_b,
            cqs_delta=cqs_delta,
            metric_deltas=metric_deltas,
            improved_metrics=improved,
            regressed_metrics=regressed,
            unchanged_metrics=unchanged,
            summary=summary,
        )
        logger.info(
            "Delta computed for %s: CQS %+.1f (%d improved, %d regressed)",
            newer.url, cqs_delta, len(improved), len(regressed)
        )
        return result

    except Exception as exc:
        logger.warning("Failed to construct AuditDelta for %s: %s", newer.url, exc)
        return None


def find_previous_audit(
    current: AuditResult,
    audit_metas: list,
) -> Optional[AuditResult]:
    """
    Find the most recent prior audit for the same URL from a list of AuditMeta objects.

    Used by audit_runner.py to automatically attach a delta when re-auditing
    a URL that has been audited before.

    Args:
        current:     The just-completed AuditResult.
        audit_metas: List of AuditMeta objects from storage.list_audits().

    Returns:
        The most recent older AuditResult for the same URL, or None.
    """
    # Import here to avoid circular import (storage imports models, delta imports models)
    from core.storage import load_audit

    current_normalised = _normalise_url(current.url)
    current_ts = current.timestamp or datetime.now(timezone.utc)

    candidates = []
    for meta in audit_metas:
        if _normalise_url(meta.url) != current_normalised:
            continue

        # Skip audits with the exact same file that would be the current one
        # (edge case: same timestamp saved twice)
        meta_ts = meta.timestamp if isinstance(meta.timestamp, datetime) else \
            datetime.fromisoformat(str(meta.timestamp))

        if meta_ts >= current_ts:
            continue

        candidates.append((meta_ts, meta))

    if not candidates:
        return None

    # Most recent older audit
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, best_meta = candidates[0]

    prior = load_audit(best_meta.file_path)
    if prior is None:
        logger.warning("Could not load prior audit from %s", best_meta.file_path)

    return prior