"""
ui/history_view.py
------------------
Previous audits sidebar panel for AiGeoPacific.

Renders a list of past audit results stored locally by core/storage.py.
Allows users to:
  - Browse saved audits (newest first)
  - Click to reload a past result without re-running the audit
  - Delete individual audits
  - Compare two audits of the same URL (when 2+ exist)

Design rules:
  - All Streamlit calls are in this file. Zero business logic here.
  - No direct imports from core/scorer.py, core/audit_runner.py, etc.
  - Reads via storage.list_audits() and storage.load_audit() only.
  - Delta computation via core/delta.compute_delta() — not here.
  - Uses session state keys: st.session_state.result, st.session_state.pdf_buffer
  - Never crashes if storage is empty or a file is corrupted.
  - No emojis in section headers or nav items (Phase 2 rule).
    Score chips use colour coding instead.

Imported by:
  - app.py: history_view.history_panel() called in sidebar
"""

import logging
from datetime import datetime
from typing import Optional

import streamlit as st

from core import storage, delta as delta_module
from core.models import AuditMeta, AuditResult

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _score_chip_html(cqs: float) -> str:
    """
    Return an HTML pill badge coloured by CQS tier.

    Args:
        cqs: Numeric CQS score (0–100).

    Returns:
        HTML string for a coloured pill badge.
    """
    if cqs >= 70:
        bg, fg, label = "#166534", "#dcfce7", f"{cqs:.0f}"
    elif cqs >= 45:
        bg, fg, label = "#92400e", "#fef3c7", f"{cqs:.0f}"
    else:
        bg, fg, label = "#991b1b", "#fee2e2", f"{cqs:.0f}"

    return (
        f'<span style="'
        f'background:{bg};color:{fg};'
        f'padding:2px 8px;border-radius:12px;'
        f'font-size:11px;font-weight:700;'
        f'font-family:DM Mono,monospace;'
        f'display:inline-block;margin-left:4px;">'
        f'{label}</span>'
    )


def _confidence_chip_html(level: str) -> str:
    """
    Return an HTML pill badge for confidence level.

    Args:
        level: "High", "Medium", or "Low"

    Returns:
        HTML string.
    """
    colours = {
        "High":   ("#166534", "#dcfce7"),
        "Medium": ("#92400e", "#fef3c7"),
        "Low":    ("#991b1b", "#fee2e2"),
    }
    bg, fg = colours.get(level, ("#374151", "#f3f4f6"))
    return (
        f'<span style="'
        f'background:{bg};color:{fg};'
        f'padding:2px 6px;border-radius:8px;'
        f'font-size:10px;font-weight:600;'
        f'display:inline-block;">'
        f'{level}</span>'
    )


def _format_timestamp(ts) -> str:
    """
    Format a timestamp (datetime or ISO string) for display.

    Args:
        ts: datetime object or ISO string.

    Returns:
        Human-readable string like "12 Apr 2026, 14:30"
    """
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return ts.strftime("%-d %b %Y, %H:%M")
    except Exception:
        return str(ts)[:16]


def _short_url(url: str, max_len: int = 40) -> str:
    """
    Shorten a URL for display in the sidebar.

    Strips scheme, truncates with ellipsis if needed.

    Args:
        url:     Full URL.
        max_len: Maximum character length.

    Returns:
        Shortened display string.
    """
    display = url.lower()
    for prefix in ("https://www.", "http://www.", "https://", "http://"):
        if display.startswith(prefix):
            display = display[len(prefix):]
            break
    if len(display) > max_len:
        display = display[:max_len - 3] + "..."
    return display


def _group_by_domain(metas: list[AuditMeta]) -> dict[str, list[AuditMeta]]:
    """
    Group AuditMeta objects by their domain for delta-comparison detection.

    Args:
        metas: List of AuditMeta from storage.list_audits().

    Returns:
        Dict mapping domain string to list of AuditMeta (newest first).
    """
    import re
    groups: dict[str, list[AuditMeta]] = {}
    for meta in metas:
        domain = re.sub(r'^https?://(www\.)?', '', meta.url.lower()).split('/')[0]
        groups.setdefault(domain, []).append(meta)
    return groups


# ------------------------------------------------------------------
# Delta display
# ------------------------------------------------------------------

def _render_delta_section(older: AuditResult, newer: AuditResult) -> None:
    """
    Compute and render a delta comparison between two audits in the sidebar.

    Displays CQS change and per-metric improved/regressed lists.
    Renders nothing if delta computation fails.

    Args:
        older: The earlier AuditResult.
        newer: The more recent AuditResult.
    """
    result = delta_module.compute_delta(older, newer)
    if result is None:
        st.warning("Could not compute delta — URLs may not match.")
        return

    # CQS delta headline
    delta_val = result.cqs_delta
    arrow = "+" if delta_val > 0 else ""
    colour = "#4ade80" if delta_val > 0 else ("#f87171" if delta_val < 0 else "#9ca3af")

    st.markdown(
        f'<p style="font-size:13px;margin:4px 0;">'
        f'<strong>CQS change:</strong> '
        f'<span style="color:{colour};font-weight:700;">{arrow}{delta_val:.1f}</span>'
        f'</p>',
        unsafe_allow_html=True,
    )
    st.caption(result.summary)

    # Improved metrics
    if result.improved_metrics:
        st.markdown(
            f'<p style="font-size:11px;color:#4ade80;margin:2px 0;">'
            f'Improved: {", ".join(result.improved_metrics)}</p>',
            unsafe_allow_html=True,
        )

    # Regressed metrics
    if result.regressed_metrics:
        st.markdown(
            f'<p style="font-size:11px;color:#f87171;margin:2px 0;">'
            f'Regressed: {", ".join(result.regressed_metrics)}</p>',
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def history_panel() -> None:
    """
    Render the full audit history panel in the Streamlit sidebar.

    Loads saved audits from local storage, displays them as clickable
    items, and shows a delta comparison when multiple audits exist
    for the same URL.

    Session state keys used:
        st.session_state.result        — set when user clicks "Load" on a history item
        st.session_state.pdf_buffer    — cleared when a historical result is loaded
        st.session_state.history_delta — stores (older, newer) for compare flow

    This function is safe to call even when storage is empty.
    """
    st.markdown(
        '<p style="font-size:11px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:#9ca3af;margin:0 0 8px 0;">'
        'Audit History</p>',
        unsafe_allow_html=True,
    )

    metas = storage.list_audits()

    if not metas:
        st.caption("No saved audits yet. Run your first audit above.")
        return

    # Storage stats footer data (used at bottom)
    stats = storage.storage_stats()
    domain_groups = _group_by_domain(metas)

    # ------------------------------------------------------------------
    # Render each audit entry
    # ------------------------------------------------------------------
    for i, meta in enumerate(metas):
        url_display = _short_url(meta.url)
        ts_display = _format_timestamp(meta.timestamp)
        score_chip = _score_chip_html(meta.cqs)
        conf_chip = _confidence_chip_html(meta.confidence_level)

        # Determine if this domain has multiple audits (enables compare)
        import re
        domain = re.sub(r'^https?://(www\.)?', '', meta.url.lower()).split('/')[0]
        domain_audit_count = len(domain_groups.get(domain, []))
        has_prior = domain_audit_count > 1

        with st.expander(f"{url_display}", expanded=False):
            # Timestamp + chips
            st.markdown(
                f'<p style="font-size:11px;color:#9ca3af;margin:0 0 4px 0;">'
                f'{ts_display} &nbsp;{score_chip}&nbsp;{conf_chip}</p>',
                unsafe_allow_html=True,
            )

            col_load, col_delete = st.columns([3, 1])

            # Load button — reloads audit into main view
            with col_load:
                if st.button(
                    "Load report",
                    key=f"history_load_{i}",
                    use_container_width=True,
                ):
                    loaded = storage.load_audit(meta.file_path)
                    if loaded:
                        st.session_state.result = loaded
                        # Clear PDF buffer — it will be regenerated when user
                        # clicks Download, not automatically on history load
                        st.session_state.pdf_buffer = None
                        st.session_state.history_delta = None
                        st.rerun()
                    else:
                        st.error("Could not load this audit. File may be corrupted.")

            # Delete button
            with col_delete:
                if st.button(
                    "Del",
                    key=f"history_delete_{i}",
                    help="Delete this audit record",
                    use_container_width=True,
                ):
                    deleted = storage.delete_audit(meta.file_path)
                    if deleted:
                        st.rerun()
                    else:
                        st.error("Could not delete this file.")

            # Compare with previous (only shown if 2+ audits for this domain)
            if has_prior and domain_audit_count >= 2:
                st.markdown(
                    '<p style="font-size:10px;color:#9ca3af;margin:6px 0 2px 0;">'
                    'Multiple audits detected for this domain.</p>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Compare with previous",
                    key=f"history_compare_{i}",
                    use_container_width=True,
                ):
                    _trigger_compare(meta, domain_groups[domain])

    # ------------------------------------------------------------------
    # Delta comparison panel (shown inline below history list)
    # ------------------------------------------------------------------
    if st.session_state.get("history_delta"):
        older_result, newer_result = st.session_state.history_delta
        st.divider()
        st.markdown(
            '<p style="font-size:11px;font-weight:700;letter-spacing:0.08em;'
            'text-transform:uppercase;color:#9ca3af;margin:0 0 6px 0;">'
            'Progress Comparison</p>',
            unsafe_allow_html=True,
        )
        _render_delta_section(older_result, newer_result)

        if st.button("Clear comparison", key="history_clear_delta"):
            st.session_state.history_delta = None
            st.rerun()

    # ------------------------------------------------------------------
    # Storage stats footer
    # ------------------------------------------------------------------
    st.markdown(
        f'<p style="font-size:10px;color:#6b7280;margin:12px 0 0 0;">'
        f'{stats["count"]}/{stats["limit"]} audits stored locally</p>',
        unsafe_allow_html=True,
    )


def _trigger_compare(selected_meta: AuditMeta, domain_metas: list[AuditMeta]) -> None:
    """
    Load the selected audit and the one immediately prior to it (same domain),
    then store both in session state for delta rendering.

    Args:
        selected_meta: The AuditMeta the user clicked "Compare" on.
        domain_metas:  All AuditMeta for the same domain (newest first).
    """
    # Sort by timestamp to find "previous" audit
    def _ts(meta: AuditMeta) -> datetime:
        ts = meta.timestamp
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return datetime.min
        return ts if isinstance(ts, datetime) else datetime.min

    sorted_metas = sorted(domain_metas, key=_ts, reverse=True)

    # Find selected_meta in sorted list
    try:
        idx = next(
            i for i, m in enumerate(sorted_metas)
            if m.file_path == selected_meta.file_path
        )
    except StopIteration:
        st.warning("Could not locate this audit in history.")
        return

    # We need the audit immediately after it in time order (i.e. index + 1)
    if idx + 1 >= len(sorted_metas):
        st.info("No earlier audit found for this domain.")
        return

    newer_meta = sorted_metas[idx]
    older_meta = sorted_metas[idx + 1]

    newer_result = storage.load_audit(newer_meta.file_path)
    older_result = storage.load_audit(older_meta.file_path)

    if newer_result is None or older_result is None:
        st.error("One or both audit files could not be loaded.")
        return

    st.session_state.history_delta = (older_result, newer_result)
    st.rerun()