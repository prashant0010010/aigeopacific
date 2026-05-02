"""
ui/results_view.py
==================
View orchestrator for the AiGeoPacific AI Citation Analyser dashboard.

Phase 2 additions:
- _render_delta_section(): CQS progress banner when prior audit exists
- _render_citation_section(): AI Citations Detected (shown ONLY if found)
- _render_prompt_visibility(): Keyword prompt visibility analysis
- All text fields sanitised via _safe_html() from components.py

Architecture:
- Zero business logic, zero HTML/CSS, zero data transformations.
- Pure view layer wiring AuditResult to component functions.
"""

import streamlit as st
from typing import Any, Optional

from core.models import AuditResult
from ui.components import (
    _safe_html,
    render_citation_event,
    render_competitor_row,
    render_confidence_indicator,
    render_delta_banner,
    render_divider,
    render_gap_insight,
    render_metric_card,
    render_progress_bar,
    render_prompt_row,
    render_quick_win,
    render_score_badge,
    render_section_header,
    render_status_banner,
)


# ===========================================================================
# Safe data accessors
# ===========================================================================


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely retrieve an attribute from an object or key from a dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr) or default
    return getattr(obj, attr, None) or default


def _safe_list(obj: Any, attr: str) -> list:
    """Return a list attribute safely, defaulting to empty list."""
    val = _get(obj, attr, [])
    return val if isinstance(val, list) else []


# ===========================================================================
# Section renderers
# ===========================================================================


def _render_status_area(result: AuditResult, pdf_buffer: Optional[bytes]) -> None:
    """
    Render the top status bar: completion banner, PDF download, confidence chip.
    """
    status = _get(result, "status", "failed")
    summary = _get(result, "audit_summary", "Audit completed.")
    confidence = _get(result, "confidence")
    conf_level = _get(confidence, "level", "Low")

    if status == "success":
        render_status_banner("success", summary)
    elif status == "partial":
        render_status_banner("warning", summary)
    else:
        render_status_banner("error", summary)

    col_conf, col_dl = st.columns([3, 1])

    with col_conf:
        render_confidence_indicator(conf_level)

    with col_dl:
        if pdf_buffer:
            url = _get(result, "url", "page")
            safe_filename = (
                url.replace("https://", "")
                   .replace("http://", "")
                   .replace("/", "_")
                   .strip("_")[:40]
            )
            st.download_button(
                label="Download PDF Report",
                data=pdf_buffer,
                file_name=f"aigeopacific_{safe_filename}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.button(
                "Generating PDF...",
                disabled=True,
                use_container_width=True,
            )


# ---------------------------------------------------------------------------
# Phase 2 — Delta section
# ---------------------------------------------------------------------------


def _render_delta_section(result: AuditResult) -> None:
    """
    Render CQS progress comparison banner.

    Shown ONLY when result.delta is populated (second+ audit of same URL).
    Skipped silently if delta is None.

    Parameters
    ----------
    result : AuditResult
    """
    delta = _get(result, "delta", None)
    if not delta:
        return

    render_section_header(
        "Progress Since Last Audit",
        subtitle="Score change compared to the previous audit of this URL",
    )

    cqs_delta = float(_get(delta, "cqs_delta", 0.0) or 0.0)
    summary = _get(delta, "summary", "")
    improved = _safe_list(delta, "improved_metrics")
    regressed = _safe_list(delta, "regressed_metrics")

    render_delta_banner(
        cqs_delta=cqs_delta,
        summary=summary,
        improved=improved,
        regressed=regressed,
    )

    render_divider()


def _render_executive_summary(result: AuditResult) -> None:
    """
    Render the Executive Summary section: CQS score, business impact, quick wins.
    """
    render_section_header(
        "Executive Summary",
        subtitle="Overall AI citation visibility and highest-leverage improvements",
    )

    enrichment = _get(result, "enrichment")
    cqs = float(_get(result, "cqs", 0) or 0)

    col_cqs, col_sp = st.columns([1, 2])

    with col_cqs:
        badge_html = render_score_badge(int(cqs))
        st.markdown(
            f"""
            <div style="
                background:    var(--bg-card);
                border:        1px solid var(--border);
                border-radius: 12px;
                padding:       1.25rem;
                text-align:    center;
            ">
                <p style="font-family:var(--font-mono); font-size:0.7rem;
                          color:var(--text-secondary); text-transform:uppercase;
                          letter-spacing:0.08em; margin-bottom:0.5rem;">
                    Citation Quality Score
                </p>
                <div style="font-family:var(--font-heading); font-size:3rem;
                            font-weight:700; color:var(--accent); line-height:1;
                            margin-bottom:0.4rem;">
                    {int(cqs)}
                </div>
                <div>{badge_html}</div>
                <p style="font-family:var(--font-body); font-size:0.75rem;
                          color:var(--text-secondary); margin-top:0.5rem;">out of 100</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_sp:
        impact = _safe_html(_get(enrichment, "business_impact", "Analysis not available."))
        st.markdown(
            f"""
            <div style="padding:0.25rem 0;">
                <p style="font-family:var(--font-mono); font-size:0.7rem;
                          color:var(--accent); text-transform:uppercase;
                          letter-spacing:0.08em; margin-bottom:0.4rem;">
                    Business Impact
                </p>
                <p style="font-family:var(--font-body); font-size:0.875rem;
                          color:var(--text-secondary); line-height:1.6; margin:0;">
                    {impact}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_divider()

    quick_wins = _safe_list(enrichment, "quick_wins")
    if quick_wins:
        st.markdown(
            '<p style="font-family:var(--font-mono); font-size:0.7rem; '
            'color:var(--accent); text-transform:uppercase; letter-spacing:0.08em; '
            'margin-bottom:0.5rem;">Quick Wins</p>',
            unsafe_allow_html=True,
        )
        for i, win in enumerate(quick_wins[:5], start=1):
            if win:
                render_quick_win(i, win)


# ---------------------------------------------------------------------------
# Phase 2 — AI Citations Detected
# ---------------------------------------------------------------------------


def _render_citation_section(result: AuditResult) -> None:
    """
    Render the AI Citations Detected section.

    CRITICAL RULE: This section renders ONLY when citations are found.
    If citations_found is empty, this function returns immediately with
    NO output — no "no citations found" banner, nothing.

    Parameters
    ----------
    result : AuditResult
    """
    citation_check = _get(result, "citation_check", None)
    if not citation_check:
        return

    citations = _safe_list(citation_check, "citations_found")
    if not citations:
        return  # Rule: no output when empty

    render_section_header(
        "AI Citations Detected",
        subtitle="Your page was cited by AI systems during this audit session",
    )

    render_status_banner(
        "success",
        f"{len(citations)} citation(s) detected across {_get(citation_check, 'checked_prompts', 0)} prompts",
    )

    for citation in citations:
        render_citation_event(
            prompt=_get(citation, "prompt", ""),
            cited_url=_get(citation, "cited_url", ""),
            level=_get(citation, "citation_level", "domain"),
            snippet=_get(citation, "context_snippet", ""),
        )

    confidence_note = _get(citation_check, "confidence_note", "")
    if confidence_note:
        st.caption(_safe_html(confidence_note))

    render_divider()


def _render_visibility_score(result: AuditResult) -> None:
    """
    Render the Visibility Score section: metric progress bars + search presence.
    """
    render_section_header(
        "Visibility Score Breakdown",
        subtitle="Weighted contribution of each signal to the final CQS",
    )

    metrics = _safe_list(result, "metrics")
    search_pres = _get(result, "search_presence")

    if not metrics:
        st.markdown(
            '<p style="color:var(--text-secondary); font-size:0.875rem;">'
            'Metric data not available.</p>',
            unsafe_allow_html=True,
        )
    else:
        for metric in metrics:
            name = _get(metric, "name", "Metric")
            score = float(_get(metric, "score", 0) or 0)
            weight = float(_get(metric, "weight", 0) or 0)
            render_progress_bar(name, int(score), weight=weight if weight > 0 else None)

    if search_pres:
        render_divider()
        sp_status = _get(search_pres, "status", "not_visible")
        sp_score = float(_get(search_pres, "score", 0) or 0)
        sp_url = _get(search_pres, "found_url", None)

        status_labels = {
            "exact_match":   ("Exact URL Match",  "success"),
            "brand_visible": ("Brand Visible",     "warning"),
            "not_visible":   ("Not Visible",       "error"),
        }
        label, banner_type = status_labels.get(
            sp_status, (sp_status.replace("_", " ").title(), "error")
        )

        render_status_banner(
            banner_type,
            f"Search Presence — {label} (score: {int(sp_score)})",
        )

        if sp_url:
            st.markdown(
                f'<p style="font-family:var(--font-mono); font-size:0.72rem; '
                f'color:var(--text-secondary); margin-top:-0.5rem;">'
                f'Matched: {_safe_html(sp_url[:80])}</p>',
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Phase 2 — Prompt Visibility Analysis
# ---------------------------------------------------------------------------


def _render_prompt_visibility(result: AuditResult) -> None:
    """
    Render the Prompt Visibility Analysis section.

    Shown ONLY when result.prompt_presence is non-empty.
    Displays each tested keyword prompt with its visibility status chip.

    Parameters
    ----------
    result : AuditResult
    """
    prompts = _safe_list(result, "prompt_presence")
    if not prompts:
        return

    render_section_header(
        "Prompt Visibility Analysis",
        subtitle="Whether your page appears when AI searches for your target queries",
    )

    for ppr in prompts:
        render_prompt_row(
            prompt=_get(ppr, "prompt", ""),
            visibility=_get(ppr, "visibility", "not_visible"),
            competitor_url=_get(ppr, "competitor_url", None),
            search_position=_get(ppr, "search_position", None),
        )

    render_divider()


def _render_metric_breakdown(result: AuditResult) -> None:
    """
    Render the Detailed Metric Analysis section: two-column metric card grid.
    """
    render_section_header(
        "Detailed Metric Analysis",
        subtitle="Per-signal scoring with AI explainability and fix guidance",
    )

    metrics = _safe_list(result, "metrics")

    if not metrics:
        st.markdown(
            '<p style="color:var(--text-secondary); font-size:0.875rem;">'
            'No metric data available for this audit.</p>',
            unsafe_allow_html=True,
        )
        return

    cols = st.columns(2)

    for i, metric in enumerate(metrics):
        name = _get(metric, "name", "Metric")
        score = int(float(_get(metric, "score", 0) or 0))
        weight = float(_get(metric, "weight", 0) or 0)
        why = _get(metric, "why_it_matters", "")
        how_ai = _get(metric, "how_ai_reads_it", "")
        what_fix = _get(metric, "what_to_fix", "")

        weight_pct = f"{int(weight * 100)}% weight" if weight > 0 else "Signal"

        with cols[i % 2]:
            render_metric_card(
                title=name,
                score=score,
                body=why or "No description available.",
                label=weight_pct,
                why_it_matters=why,
                how_ai_reads_it=how_ai,
                what_to_fix=what_fix,
            )


def _render_competitor_comparison(result: AuditResult) -> None:
    """
    Render the Competitor Benchmarking section: table + gap insights.
    """
    render_section_header(
        "Competitor Benchmarking",
        subtitle="How top-ranking pages compare against your Citation Quality Score",
    )

    comparison = _get(result, "competitor_comparison")
    competitors = _safe_list(comparison, "competitors")
    gaps = _safe_list(comparison, "gaps")

    if not competitors:
        st.markdown(
            '<p style="color:var(--text-secondary); font-size:0.875rem;">'
            'Competitor data could not be collected for this audit.</p>',
            unsafe_allow_html=True,
        )
    else:
        render_competitor_row("Competitor URL", "CQS", is_header=True)
        for comp in competitors:
            url_val = _get(comp, "competitor_url", "Unknown")
            cqs_val = int(float(_get(comp, "cqs", 0) or 0))
            render_competitor_row(url_val, cqs_val)
        st.markdown("<div style='margin-bottom:0.25rem;'></div>", unsafe_allow_html=True)

    if gaps:
        render_divider()
        st.markdown(
            '<p style="font-family:var(--font-mono); font-size:0.7rem; '
            'color:var(--accent); text-transform:uppercase; letter-spacing:0.08em; '
            'margin-bottom:0.5rem;">Gap Insights</p>',
            unsafe_allow_html=True,
        )
        for gap in gaps:
            if gap:
                render_gap_insight(gap)


def _render_priority_fix_plan(result: AuditResult) -> None:
    """
    Render the Priority Fix Plan section: recommendations grouped by tier.

    Phase 2 rule: emojis KEPT here only (🔥 ⚙️ 🚀 in tier labels).
    """
    render_section_header(
        "Priority Fix Plan",
        subtitle="Ranked actions to improve AI citation visibility",
    )

    enrichment = _get(result, "enrichment")
    recommendations = _safe_list(enrichment, "recommendations")

    if not recommendations:
        metrics = _safe_list(result, "metrics")
        for m in sorted(metrics, key=lambda x: float(_get(x, "score", 100) or 100)):
            fix = _get(m, "what_to_fix", "")
            score = float(_get(m, "score", 100) or 100)
            if fix and score < 60:
                tier = "🔥" if score < 35 else "⚙️"
                recommendations.append({"priority": tier, "action": fix})

    if not recommendations:
        st.markdown(
            '<p style="color:var(--text-secondary); font-size:0.875rem;">'
            'No recommendations available.</p>',
            unsafe_allow_html=True,
        )
        return

    tiers = {
        "🔥": ("High Priority",         "var(--score-red-text)"),
        "⚙️": ("Medium Priority",       "var(--score-amber-text)"),
        "🚀": ("Long-Term Optimization", "#93c5fd"),
    }

    grouped: dict = {"🔥": [], "⚙️": [], "🚀": []}

    for rec in recommendations:
        if isinstance(rec, dict):
            priority = rec.get("priority", "⚙️") or "⚙️"
            action = rec.get("action", "") or ""
        else:
            priority, action = "⚙️", str(rec)

        tier_key = next((k for k in grouped if k in priority), "⚙️")
        if action:
            grouped[tier_key].append(action)

    for emoji, (tier_label, accent) in tiers.items():
        items = grouped[emoji]
        if not items:
            continue

        st.markdown(
            f'<p style="font-family:var(--font-mono); font-size:0.75rem; '
            f'font-weight:600; color:{accent}; text-transform:uppercase; '
            f'letter-spacing:0.07em; margin-top:1rem; margin-bottom:0.4rem;">'
            f'{emoji}  {tier_label}</p>',
            unsafe_allow_html=True,
        )

        for action in items:
            st.markdown(
                f'<div style="display:flex; align-items:flex-start; gap:0.5rem; '
                f'margin-bottom:0.4rem; padding-left:0.5rem;">'
                f'<span style="color:{accent}; font-size:0.8rem; '
                f'flex-shrink:0; margin-top:2px;">•</span>'
                f'<span style="font-family:var(--font-body); font-size:0.875rem; '
                f'color:var(--text-primary); line-height:1.55;">'
                f'{_safe_html(action)}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ===========================================================================
# Primary public function
# ===========================================================================


def render_audit_results(
    result: AuditResult,
    pdf_buffer: Optional[bytes] = None,
) -> None:
    """
    Render the complete AiGeoPacific audit results dashboard.

    Phase 2 section order:
    1. Status area (always)
    2. Progress Since Last Audit (ONLY if delta exists)
    3. Executive Summary (always)
    4. AI Citations Detected (ONLY if citations found)
    5. Visibility Score (always)
    6. Prompt Visibility Analysis (ONLY if prompts tested)
    7. Competitor Benchmarking (always)
    8. Detailed Metric Analysis (always)
    9. Priority Fix Plan (always)

    Parameters
    ----------
    result : AuditResult
    pdf_buffer : Optional[bytes]
    """
    if result is None:
        render_status_banner(
            "error",
            "No audit result available. Please run an audit first.",
        )
        return

    _render_status_area(result, pdf_buffer)
    render_divider()

    # Conditional: delta (shown only if previous audit exists)
    _render_delta_section(result)

    _render_executive_summary(result)
    render_divider()

    # Conditional: citations (shown only if found)
    _render_citation_section(result)

    _render_visibility_score(result)
    render_divider()

    # Conditional: prompt visibility (shown only if prompts tested)
    _render_prompt_visibility(result)

    _render_competitor_comparison(result)
    render_divider()

    _render_metric_breakdown(result)
    render_divider()

    _render_priority_fix_plan(result)