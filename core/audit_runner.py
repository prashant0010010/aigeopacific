"""
core/audit_runner.py
====================
Pipeline orchestrator for the AiGeoPacific AI Citation Analyser.

Phase 2 additions:
- Enrichment routing: Gemini first, heuristic fallback (_get_enrichment)
- Citation check integration: check_citations() called when prompts exist
- Prompt presence: check_prompt_presence() run per keyword prompt
- Delta wiring: find_previous_audit() + compute_delta() auto-attached
- save_audit() called after every successful audit

This module contains zero scoring logic. It is a pure coordinator.
"""

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from core import competitor, confidence, fetcher, scorer
from core.delta import compute_delta, find_previous_audit
from core.models import (
    AuditResult,
    CompetitorComparison,
    ConfidenceResult,
    EnrichmentResult,
    MetricScore,
    PageConfig,
    SearchPresence,
)
from core.storage import list_audits, save_audit
from services import search_service
from services.citation_service import check_citations

# ---------------------------------------------------------------------------
# Status and summary mappings
# ---------------------------------------------------------------------------

_STATUS_MESSAGES = {
    "success": "Full page access",
    "limited_access": "Limited access detected",
    "failed": "Page could not be retrieved",
}

_AUDIT_SUMMARIES = {
    "success": "Success: Full analysis completed.",
    "limited_access": "Caution: Limited page access may reduce scoring accuracy.",
    "failed": "Audit incomplete: Unable to retrieve page.",
}


# ---------------------------------------------------------------------------
# Safe fallback objects
# ---------------------------------------------------------------------------

def _safe_search_presence() -> SearchPresence:
    """Return a neutral SearchPresence used when search data is unavailable."""
    return SearchPresence(
        status="not_visible",
        score=0.0,
        found_url=None,
        matched_text="Search data unavailable",
    )


def _safe_competitor_comparison() -> CompetitorComparison:
    """Return an empty CompetitorComparison used when analysis cannot run."""
    return CompetitorComparison(
        competitors=[],
        gaps=["Competitor analysis could not be completed."],
    )


def _safe_confidence(level: str = "Low", reasoning: str = "") -> ConfidenceResult:
    """Return a fallback ConfidenceResult."""
    return ConfidenceResult(
        level=level,
        reasoning=reasoning or "Confidence could not be calculated.",
    )


def _safe_enrichment() -> EnrichmentResult:
    """Return a minimal EnrichmentResult placeholder."""
    return EnrichmentResult(
        business_impact=(
            "Unable to generate enrichment. "
            "Please re-run the audit or provide a Gemini API key."
        ),
        quick_wins=[],
        recommendations=[],
        ideal_targets={},
        competitor_insight=[],
        llm_key_signals={},
        suggested_search_prompts=[],
    )


def _failed_audit_result(url: str, summary: str) -> AuditResult:
    """
    Construct a fully valid AuditResult representing a failed audit.

    Every field is populated so the PDF builder and UI never receive
    a partially-constructed object.
    """
    return AuditResult(
        url=url,
        cqs=0.0,
        metrics=[],
        search_presence=_safe_search_presence(),
        competitor_comparison=_safe_competitor_comparison(),
        confidence=_safe_confidence(
            level="Low",
            reasoning="Audit could not be completed due to a fetch failure or system error.",
        ),
        enrichment=_safe_enrichment(),
        status="failed",
        status_message=_STATUS_MESSAGES["failed"],
        audit_summary=summary,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Timing helper
# ---------------------------------------------------------------------------

def _elapsed(start: float) -> str:
    """Return a formatted elapsed-time string from a start timestamp."""
    return f"{time.time() - start:.2f}s"


# ---------------------------------------------------------------------------
# Phase 2 — Enrichment routing
# ---------------------------------------------------------------------------

def _get_enrichment(result: AuditResult, config: PageConfig) -> EnrichmentResult:
    """
    Route enrichment through Gemini (if API key present) with automatic
    heuristic fallback.

    Tries Gemini first. On any exception (network, quota, invalid key),
    falls through to heuristic_service.enrich(). The heuristic service
    produces the same EnrichmentResult structure without any API calls.

    This function never raises — it always returns a valid EnrichmentResult.

    Parameters
    ----------
    result : AuditResult
        Partially assembled audit result (metrics + cqs populated).
    config : PageConfig
        Contains gemini_api_key if the user provided one.

    Returns
    -------
    EnrichmentResult
    """
    gemini_key = getattr(config, "gemini_api_key", None)

    if gemini_key:
        try:
            from services.gemini_service import enrich as gemini_enrich
            enrichment = gemini_enrich(result)
            if enrichment:
                print("[Audit] Enrichment: Gemini succeeded.")
                return enrichment
        except Exception as exc:
            print(f"[Audit] Enrichment: Gemini failed ({exc}), falling back to heuristic.")

    try:
        from services.heuristic_service import enrich as heuristic_enrich
        enrichment = heuristic_enrich(result)
        if enrichment:
            print("[Audit] Enrichment: Heuristic succeeded.")
            return enrichment
    except Exception as exc:
        print(f"[Audit] Enrichment: Heuristic also failed ({exc}). Using safe fallback.")

    return _safe_enrichment()


# ===========================================================================
# Main orchestrator
# ===========================================================================

def run_audit(config: PageConfig) -> AuditResult:
    """
    Execute the full AiGeoPacific audit pipeline for a single page.

    Pipeline stages (Phase 2):
    1.  Fetch page content
    2.  Early exit if page could not be retrieved
    3.  Run scorer and search service in parallel
    4.  Run competitor analysis (concurrent fetch, Phase 2)
    5.  Calculate confidence
    6.  Route enrichment (Gemini -> heuristic)
    7.  Run prompt presence checks (if keyword_prompts provided)
    8.  Run citation detection (if prompts + optional Perplexity key)
    9.  Assemble AuditResult
    10. Save audit to local storage
    11. Compute delta against previous audit (if one exists)

    This function never raises. All exceptions are caught at the top level.

    Parameters
    ----------
    config : PageConfig

    Returns
    -------
    AuditResult — always fully populated, always valid.
    """
    audit_start = time.time()

    try:
        # ===================================================================
        # Step 1 — Fetch Page
        # ===================================================================
        print(f"[Audit] Step 1 — Fetching: {config.url}")
        step_start = time.time()

        page_data = fetcher.fetch_page(config.url)
        fetch_status = page_data.get("status", "failed")

        print(f"[Audit] Step 1 complete — status: {fetch_status} ({_elapsed(step_start)})")

        # ===================================================================
        # Step 2 — Early exit
        # ===================================================================
        if fetch_status == "failed":
            print("[Audit] Step 2 — Early exit: page fetch failed.")
            return _failed_audit_result(
                url=config.url,
                summary=_AUDIT_SUMMARIES["failed"],
            )

        # ===================================================================
        # Step 3 — Parallel: Scorer + Search Service
        # ===================================================================
        print("[Audit] Step 3 — Scorer + search in parallel")
        step_start = time.time()

        metric_scores: list = []
        cqs: float = 0.0
        presence: SearchPresence = _safe_search_presence()

        def _run_scorer():
            scores, final_cqs, debug = scorer.compute_cqs(
                page_config=config,
                page_data=page_data,
                search_presence=0.0,
            )
            return scores, final_cqs, debug

        def _run_search():
            return search_service.check_search_presence(
                url=config.url,
                brand_name=config.brand_name,
                page_title=page_data.get("title"),
            )

        scorer_result = None
        search_result = None

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_scorer = executor.submit(_run_scorer)
            future_search = executor.submit(_run_search)

            for future in as_completed([future_scorer, future_search]):
                if future is future_scorer:
                    try:
                        scorer_result = future.result()
                        print(f"[Audit] Step 3a — Scorer done ({_elapsed(step_start)})")
                    except Exception as exc:
                        print(f"[Audit] Step 3a — Scorer failed: {exc}")
                        scorer_result = ([], 0.0, {})
                elif future is future_search:
                    try:
                        search_result = future.result()
                        print(f"[Audit] Step 3b — Search done ({_elapsed(step_start)})")
                    except Exception as exc:
                        print(f"[Audit] Step 3b — Search failed: {exc}")
                        search_result = _safe_search_presence()

        if scorer_result:
            metric_scores, cqs, _ = scorer_result

        if search_result and isinstance(search_result, SearchPresence):
            presence = search_result

        # Re-score with real search presence value
        if presence.score > 0.0:
            metric_scores, cqs, _ = scorer.compute_cqs(
                page_config=config,
                page_data=page_data,
                search_presence=presence.score,
            )

        print(f"[Audit] Step 3 complete — CQS: {cqs} ({_elapsed(step_start)})")

        # ===================================================================
        # Step 4 — Competitor Analysis (concurrent, Phase 2)
        # ===================================================================
        print("[Audit] Step 4 — Competitor analysis")
        step_start = time.time()

        competitor_comparison: CompetitorComparison = _safe_competitor_comparison()

        try:
            raw_results = search_service.run_search(
                search_service.infer_query(
                    url=config.url,
                    brand_name=config.brand_name,
                    page_title=page_data.get("title"),
                )
            )

            competitor_comparison = competitor.analyze_competitors(
                search_results=raw_results,
                user_metrics=metric_scores,
                page_config=config,
            )
            print(
                f"[Audit] Step 4 complete — "
                f"{len(competitor_comparison.competitors)} competitors ({_elapsed(step_start)})"
            )
        except Exception as exc:
            print(f"[Audit] Step 4 — Competitor analysis failed: {exc}")

        # ===================================================================
        # Step 5 — Confidence Calculation
        # ===================================================================
        print("[Audit] Step 5 — Confidence")
        step_start = time.time()

        conf_result: ConfidenceResult = _safe_confidence()

        try:
            conf_result = confidence.calculate_confidence(
                page_data=page_data,
                search_presence=presence,
                metric_scores=metric_scores,
                page_config=config,
            )
            print(
                f"[Audit] Step 5 complete — "
                f"confidence: {conf_result.level} ({_elapsed(step_start)})"
            )
        except Exception as exc:
            print(f"[Audit] Step 5 — Confidence failed: {exc}")

        # ===================================================================
        # Step 6 — Enrichment routing (Phase 2)
        # ===================================================================
        print("[Audit] Step 6 — Enrichment routing")
        step_start = time.time()

        # Assemble partial result first so enrichment has full metric context
        if fetch_status == "success":
            pipeline_status = "success"
        elif fetch_status == "limited_access":
            pipeline_status = "partial"
        else:
            pipeline_status = "failed"

        status_message = _STATUS_MESSAGES.get(fetch_status, "Unknown")
        audit_summary = _AUDIT_SUMMARIES.get(fetch_status, "Audit completed with unknown status.")

        partial_result = AuditResult(
            url=config.url,
            cqs=cqs,
            metrics=metric_scores,
            search_presence=presence,
            competitor_comparison=competitor_comparison,
            confidence=conf_result,
            enrichment=_safe_enrichment(),
            status=pipeline_status,
            status_message=status_message,
            audit_summary=audit_summary,
            timestamp=datetime.now(timezone.utc),
        )

        enrichment = _get_enrichment(partial_result, config)
        partial_result.enrichment = enrichment
        print(f"[Audit] Step 6 complete ({_elapsed(step_start)})")

        # ===================================================================
        # Step 7 — Prompt Presence (Phase 2)
        # ===================================================================
        keyword_prompts = getattr(config, "keyword_prompts", []) or []
        prompt_presence_results = []

        if keyword_prompts:
            print(f"[Audit] Step 7 — Prompt presence for {len(keyword_prompts)} prompts")
            step_start = time.time()

            from core.models import PromptPresenceResult
            full_domain = search_service.extract_domain_full(config.url)

            for prompt in keyword_prompts:
                try:
                    ppr = search_service.check_prompt_presence(
                        url=config.url,
                        domain=full_domain,
                        prompt=prompt,
                    )
                    prompt_presence_results.append(ppr)
                except Exception as exc:
                    print(f"[Audit] Prompt presence failed for '{prompt}': {exc}")

            partial_result.prompt_presence = prompt_presence_results
            print(f"[Audit] Step 7 complete ({_elapsed(step_start)})")

        # ===================================================================
        # Step 8 — Citation Detection (Phase 2)
        # ===================================================================
        perplexity_key = getattr(config, "perplexity_api_key", None)

        # Run citations if we have prompts to test (either keyword_prompts
        # or enrichment-suggested prompts as fallback)
        prompts_for_citation = keyword_prompts or []
        if not prompts_for_citation and enrichment:
            prompts_for_citation = (
                getattr(enrichment, "suggested_search_prompts", []) or []
            )[:3]  # cap at 3 to keep audit time reasonable

        if prompts_for_citation:
            print(f"[Audit] Step 8 — Citation detection ({len(prompts_for_citation)} prompts)")
            step_start = time.time()

            try:
                from urllib.parse import urlparse
                target_domain = urlparse(config.url).hostname or ""
                target_domain = target_domain.lstrip("www.")

                citation_result = check_citations(
                    prompts=prompts_for_citation,
                    target_url=config.url,
                    target_domain=target_domain,
                    api_key=perplexity_key,
                )
                partial_result.citation_check = citation_result
                found_count = len(citation_result.citations_found)
                print(
                    f"[Audit] Step 8 complete — "
                    f"{found_count} citation(s) found via {citation_result.method_used} "
                    f"({_elapsed(step_start)})"
                )
            except Exception as exc:
                print(f"[Audit] Step 8 — Citation detection failed: {exc}")

        # ===================================================================
        # Step 9 — Assemble final AuditResult
        # ===================================================================
        result = partial_result
        result.confidence_level = conf_result.level   # top-level field for AuditMeta

        # ===================================================================
        # Step 10 — Save to local storage (Phase 2)
        # ===================================================================
        try:
            saved_path = save_audit(result)
            print(f"[Audit] Step 10 — Saved: {saved_path}")
        except Exception as exc:
            print(f"[Audit] Step 10 — Save failed (non-fatal): {exc}")

        # ===================================================================
        # Step 11 — Delta comparison against previous audit (Phase 2)
        # ===================================================================
        try:
            prior_metas = list_audits()
            prior_result = find_previous_audit(result, prior_metas)
            if prior_result:
                delta = compute_delta(prior_result, result)
                result.delta = delta
                if delta:
                    print(f"[Audit] Step 11 — Delta: {delta.summary}")
        except Exception as exc:
            print(f"[Audit] Step 11 — Delta failed (non-fatal): {exc}")

        total = _elapsed(audit_start)
        print(
            f"[Audit] Pipeline complete — "
            f"total: {total} | CQS: {cqs:.1f} | "
            f"Status: {pipeline_status} | Confidence: {conf_result.level}"
        )

        return result

    # =======================================================================
    # Global catch-all
    # =======================================================================
    except Exception:
        print("[Audit] CRITICAL — Unexpected error in audit pipeline:")
        traceback.print_exc()
        return _failed_audit_result(
            url=getattr(config, "url", "unknown"),
            summary="System error occurred during audit.",
        )