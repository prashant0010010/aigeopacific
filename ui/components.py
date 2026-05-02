"""
ui/components.py
================
Reusable Streamlit UI component library for the AiGeoPacific AI Citation Analyser.

Phase 2 additions:
- _safe_html(): strips HTML tags and escapes special chars from scraped content
- Emoji cleanup: emojis removed from section headers, status banners,
  metric names, confidence labels. Kept ONLY in Priority Fix Plan tier labels.
- render_citation_event(): displays a single AI citation found
- render_prompt_row(): displays keyword prompt visibility result
- render_delta_banner(): CQS progress comparison strip

Architecture rules:
- View layer only — no scoring logic, no API calls, no data processing
- No ReportLab, no PDF references, no reports/ module imports
- All rendering uses st.markdown() with inline or class-based HTML
"""

import html as _html_lib
import re
import streamlit as st
from typing import Optional


# ===========================================================================
# Phase 2 — HTML safety helper
# ===========================================================================


def _safe_html(text: str) -> str:
    """
    Strip HTML tags from a string and escape remaining special characters.

    Apply to any string that originates from:
    - Scraped page content (titles, snippets, competitor descriptions)
    - Enrichment text from Gemini (may inject markdown or stray tags)
    - Any user-supplied or external-source text rendered into HTML

    Parameters
    ----------
    text : str
        Raw string, potentially containing HTML tags or special characters.

    Returns
    -------
    str
        Clean, safe string suitable for embedding in HTML templates.
    """
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", str(text))
    # Escape &, <, >, ", '
    return _html_lib.escape(clean)


# ===========================================================================
# Score Badge (returns HTML — used internally)
# ===========================================================================


def render_score_badge(score: int) -> str:
    """
    Return an HTML string for a colored score badge pill.

    Applies one of three badge classes based on score band:
    - badge-strong  (green)  score >= 70
    - badge-fair    (amber)  score >= 45
    - badge-weak    (red)    score <  45

    Parameters
    ----------
    score : int
    Returns
    -------
    str  HTML <span> element.
    """
    score = max(0, min(100, int(score) if score is not None else 0))

    if score >= 70:
        css_class, label = "badge-strong", "Strong"
    elif score >= 45:
        css_class, label = "badge-fair", "Fair"
    else:
        css_class, label = "badge-weak", "Weak"

    return (
        f'<span class="{css_class}" '
        f'style="font-size:0.75rem; padding:3px 10px; border-radius:999px;">'
        f'{score} &nbsp; {label}'
        f'</span>'
    )


# ===========================================================================
# Metric Card (Phase 2: redesigned, _safe_html applied)
# ===========================================================================


def render_metric_card(
    title: str,
    score: int,
    body: str,
    label: str,
    why_it_matters: Optional[str] = None,
    how_ai_reads_it: Optional[str] = None,
    what_to_fix: Optional[str] = None,
) -> None:
    """
    Render a full metric audit card into the Streamlit dashboard.

    Phase 2: all text fields are sanitised via _safe_html() before rendering.
    No emojis in title or label — colour-coded badge replaces them.

    Parameters
    ----------
    title : str
    score : int
    body : str
    label : str
    why_it_matters : Optional[str]
    how_ai_reads_it : Optional[str]
    what_to_fix : Optional[str]
    """
    score_val = max(0, min(100, int(score) if score is not None else 0))
    badge_html = render_score_badge(score_val)

    # Sanitise all text inputs
    safe_title = _safe_html(title)
    safe_body = _safe_html(body)
    safe_label = _safe_html(label)

    if score_val >= 70:
        score_color = "var(--accent)"
    elif score_val >= 45:
        score_color = "var(--score-amber-text)"
    else:
        score_color = "var(--score-red-text)"

    explainability_html = ""
    if why_it_matters or how_ai_reads_it or what_to_fix:
        explainability_html = (
            '<div style="margin-top:1rem; border-top:1px solid var(--border); '
            'padding-top:0.75rem;">'
        )
        if why_it_matters:
            explainability_html += (
                f'<p class="gold-label" style="margin-bottom:2px;">Why it matters</p>'
                f'<p class="dim-text" style="margin-bottom:0.75rem; font-size:0.82rem;">'
                f'{_safe_html(why_it_matters)}</p>'
            )
        if how_ai_reads_it:
            explainability_html += (
                f'<p class="gold-label" style="margin-bottom:2px;">How AI reads it</p>'
                f'<p class="dim-text" style="margin-bottom:0.75rem; font-size:0.82rem;">'
                f'{_safe_html(how_ai_reads_it)}</p>'
            )
        if what_to_fix:
            explainability_html += (
                f'<p class="gold-label" style="margin-bottom:2px;">What to fix</p>'
                f'<p class="dim-text" style="margin-bottom:0; font-size:0.82rem;">'
                f'{_safe_html(what_to_fix)}</p>'
            )
        explainability_html += "</div>"

    html = f"""
        <div class="metric-card">
            <div style="display:flex; justify-content:space-between;
                        align-items:flex-start; margin-bottom:0.5rem;">
                <span class="metric-card-title">{safe_title}</span>
                {badge_html}
            </div>
            <div class="metric-card-score" style="font-size:2.25rem; color:{score_color};">
                {score_val}
                <span style="font-size:1rem; color:var(--text-secondary);
                             font-family:var(--font-body);">/ 100</span>
            </div>
            <div class="metric-card-label" style="margin-bottom:0.5rem;">{safe_label}</div>
            <div class="metric-card-body">{safe_body}</div>
            {explainability_html}
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Section Header (Phase 2: no emojis)
# ===========================================================================


def render_section_header(
    title: str,
    subtitle: Optional[str] = None,
) -> None:
    """
    Render an editorial section header.

    Phase 2: no emojis in title. Uses Syne Bold + gold left border for
    visual hierarchy instead of emoji icons.

    Parameters
    ----------
    title : str
    subtitle : Optional[str]
    """
    safe_title = _safe_html(title)
    subtitle_html = ""
    if subtitle:
        subtitle_html = (
            f'<p class="dim-text" style="margin:0.25rem 0 0 0; font-size:0.875rem;">'
            f'{_safe_html(subtitle)}</p>'
        )

    html = f"""
        <div class="section-header" style="
            border-left:   3px solid var(--accent);
            padding-left:  0.875rem;
            margin-bottom: 1.25rem;
            margin-top:    1.75rem;
        ">
            <h2 style="
                font-family:    var(--font-heading);
                font-size:      1.2rem;
                font-weight:    700;
                color:          var(--accent);
                margin:         0;
                letter-spacing: -0.01em;
                text-transform: uppercase;
            ">{safe_title}</h2>
            {subtitle_html}
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Confidence Indicator (Phase 2: no emojis — colour chip only)
# ===========================================================================


def render_confidence_indicator(level: str) -> None:
    """
    Render a styled confidence level chip.

    Phase 2: no emoji prefix. Colour-coded pill badge only.

    Parameters
    ----------
    level : str  "High", "Medium", or "Low"
    """
    level_clean = (level or "Low").strip().title()

    style_map = {
        "High":   ("background:var(--score-green-bg); color:var(--score-green-text); "
                   "border:1px solid var(--score-green-bg);", "High Confidence"),
        "Medium": ("background:var(--score-amber-bg); color:var(--score-amber-text); "
                   "border:1px solid var(--score-amber-bg);", "Medium Confidence"),
        "Low":    ("background:var(--score-red-bg); color:var(--score-red-text); "
                   "border:1px solid var(--score-red-bg);", "Low Confidence"),
    }

    chip_style, display_label = style_map.get(
        level_clean,
        ("background:var(--bg-secondary); color:var(--text-secondary); "
         "border:1px solid var(--border);", level_clean),
    )

    html = f"""
        <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.75rem;">
            <span class="metric-card-label" style="color:var(--text-secondary);">
                Audit Confidence
            </span>
            <span class="confidence-chip" style="
                {chip_style}
                font-family:    var(--font-mono);
                font-size:      0.72rem;
                font-weight:    600;
                padding:        3px 12px;
                border-radius:  999px;
                letter-spacing: 0.06em;
                white-space:    nowrap;
            ">
                {display_label}
            </span>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Gap Insight
# ===========================================================================


def render_gap_insight(text: str) -> None:
    """
    Render a single styled competitor gap insight item.

    Phase 2: text is sanitised via _safe_html().

    Parameters
    ----------
    text : str
    """
    if not text or not text.strip():
        return

    html = f"""
        <div class="gap-item" style="
            display:       flex;
            align-items:   flex-start;
            gap:           0.5rem;
            margin-bottom: 0.5rem;
            padding:       0.5rem 0.75rem;
            background:    rgba(245,184,0,0.04);
            border-left:   2px solid rgba(245,184,0,0.3);
            border-radius: 0 6px 6px 0;
        ">
            <span style="color:var(--accent); flex-shrink:0; margin-top:1px;
                         font-family:var(--font-mono); font-size:0.75rem;">-&gt;</span>
            <span style="font-family:var(--font-body); font-size:0.875rem;
                         color:var(--text-primary); line-height:1.5;">
                {_safe_html(text)}
            </span>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Progress Bar
# ===========================================================================


def render_progress_bar(
    label: str,
    score: int,
    weight: Optional[float] = None,
) -> None:
    """
    Render a custom styled progress bar for a metric score.

    Parameters
    ----------
    label : str
    score : int
    weight : Optional[float]
    """
    score_val = max(0, min(100, int(score) if score is not None else 0))
    fill_pct = max(0.5, score_val)

    if score_val >= 70:
        fill_color = "var(--score-green-bg)"
        text_color = "var(--score-green-text)"
    elif score_val >= 45:
        fill_color = "var(--score-amber-bg)"
        text_color = "var(--score-amber-text)"
    else:
        fill_color = "var(--score-red-bg)"
        text_color = "var(--score-red-text)"

    weight_tag = ""
    if weight is not None:
        weight_tag = (
            f'<span class="tag-pill" style="margin-left:6px; font-size:0.65rem;">'
            f'{int(weight * 100)}% weight'
            f'</span>'
        )

    html = f"""
        <div style="margin-bottom:0.85rem;">
            <div style="display:flex; justify-content:space-between;
                        align-items:center; margin-bottom:0.3rem;">
                <span style="font-family:var(--font-mono); font-size:0.75rem;
                             color:var(--text-secondary); text-transform:uppercase;
                             letter-spacing:0.05em;">{_safe_html(label)}{weight_tag}</span>
                <span style="font-family:var(--font-mono); font-size:0.75rem;
                             color:{text_color}; font-weight:600;">{score_val}</span>
            </div>
            <div style="background:var(--border); border-radius:999px;
                        height:8px; width:100%; overflow:hidden;">
                <div style="background:{fill_color}; width:{fill_pct}%;
                            height:100%; border-radius:999px;
                            transition:width 0.4s ease;"></div>
            </div>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Status Banner (Phase 2: no emojis in banner type labels)
# ===========================================================================


def render_status_banner(
    status: str,
    message: str,
    icon: Optional[str] = None,
) -> None:
    """
    Render a full-width status banner.

    Phase 2: icon parameter kept for callers that pass emoji icons
    (Priority Fix Plan tier labels), but the banner itself uses
    CSS variable colours rather than hardcoded hex.

    Parameters
    ----------
    status : str  "success" | "warning" | "error"
    message : str
    icon : Optional[str]
    """
    style_map = {
        "success": ("rgba(22,101,52,0.25)",  "var(--score-green-text)", "var(--score-green-bg)"),
        "warning": ("rgba(146,64,14,0.25)",  "var(--score-amber-text)", "var(--score-amber-bg)"),
        "error":   ("rgba(153,27,27,0.25)",  "var(--score-red-text)",   "var(--score-red-bg)"),
    }

    bg_color, text_color, border_color = style_map.get(
        status.lower(),
        ("rgba(55,65,81,0.25)", "var(--text-secondary)", "var(--border)"),
    )

    prefix = f"{icon} " if icon else ""
    safe_message = _safe_html(message)

    html = f"""
        <div style="
            background:    {bg_color};
            border:        1px solid {border_color};
            border-radius: 10px;
            padding:       0.75rem 1.25rem;
            margin-bottom: 1rem;
            font-family:   var(--font-body);
            font-size:     0.875rem;
            color:         {text_color};
            line-height:   1.5;
        ">
            {prefix}{safe_message}
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Quick Win Item
# ===========================================================================


def render_quick_win(index: int, text: str) -> None:
    """
    Render a single numbered quick-win action item.

    Parameters
    ----------
    index : int  1-based number
    text : str
    """
    if not text or not text.strip():
        return

    html = f"""
        <div style="
            display:       flex;
            align-items:   flex-start;
            gap:           0.75rem;
            margin-bottom: 0.75rem;
            padding:       0.65rem 1rem;
            background:    var(--bg-card);
            border:        1px solid var(--border);
            border-radius: 10px;
        ">
            <div style="
                background:      var(--accent);
                color:           #0a0c10;
                font-family:     var(--font-mono);
                font-size:       0.7rem;
                font-weight:     700;
                width:           22px;
                height:          22px;
                border-radius:   50%;
                display:         flex;
                align-items:     center;
                justify-content: center;
                flex-shrink:     0;
                margin-top:      1px;
            ">{index}</div>
            <span style="font-family:var(--font-body); font-size:0.875rem;
                         color:var(--text-primary); line-height:1.5;">
                {_safe_html(text)}
            </span>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Competitor Row
# ===========================================================================


def render_competitor_row(
    url: str,
    cqs: int,
    is_header: bool = False,
) -> None:
    """
    Render a single row in the competitor comparison table.

    Parameters
    ----------
    url : str
    cqs : int
    is_header : bool
    """
    if is_header:
        html = f"""
            <div style="
                display:               grid;
                grid-template-columns: 1fr 80px 100px;
                gap:                   0.5rem;
                padding:               0.5rem 0.75rem;
                background:            var(--border);
                border-radius:         8px 8px 0 0;
                margin-bottom:         1px;
            ">
                <span style="font-family:var(--font-mono); font-size:0.7rem;
                             color:var(--accent); text-transform:uppercase;
                             letter-spacing:0.07em;">{_safe_html(str(url))}</span>
                <span style="font-family:var(--font-mono); font-size:0.7rem;
                             color:var(--accent); text-transform:uppercase;
                             letter-spacing:0.07em;">{_safe_html(str(cqs))}</span>
                <span style="font-family:var(--font-mono); font-size:0.7rem;
                             color:var(--accent); text-transform:uppercase;
                             letter-spacing:0.07em;">Strength</span>
            </div>
        """
    else:
        cqs_val = max(0, min(100, int(cqs) if cqs is not None else 0))
        badge = render_score_badge(cqs_val)
        short_url = _safe_html(url[:55] + ("..." if len(url) > 55 else ""))

        html = f"""
            <div style="
                display:               grid;
                grid-template-columns: 1fr 80px 100px;
                gap:                   0.5rem;
                padding:               0.5rem 0.75rem;
                background:            var(--bg-card);
                border-bottom:         1px solid var(--border);
                align-items:           center;
            ">
                <span style="font-family:var(--font-mono); font-size:0.75rem;
                             color:var(--text-secondary); overflow:hidden;
                             text-overflow:ellipsis; white-space:nowrap;"
                      title="{_safe_html(url)}">{short_url}</span>
                <span style="font-family:var(--font-mono); font-size:0.85rem;
                             color:var(--text-primary); font-weight:600;">{cqs_val}</span>
                <span>{badge}</span>
            </div>
        """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Phase 2 — Citation Event Card
# ===========================================================================


def render_citation_event(prompt: str, cited_url: str, level: str, snippet: str) -> None:
    """
    Render a single AI citation detection result.

    Displayed only when citations ARE found (callers must gate on this).
    Shows the prompt that triggered the citation, the cited URL, level
    (page vs domain), and the context snippet from the AI response.

    Parameters
    ----------
    prompt : str     The keyword prompt that triggered the citation.
    cited_url : str  The URL the AI cited.
    level : str      "page" (exact URL match) or "domain" (same domain).
    snippet : str    Context from the AI response (max 200 chars).
    """
    level_label = "Exact page cited" if level == "page" else "Domain cited"
    level_color = "var(--score-green-text)" if level == "page" else "var(--score-amber-text)"
    level_bg = "var(--score-green-bg)" if level == "page" else "var(--score-amber-bg)"

    html = f"""
        <div class="citation-card" style="
            background:    rgba(22,101,52,0.1);
            border:        1px solid rgba(34,197,94,0.25);
            border-radius: var(--radius-md);
            padding:       0.75rem 1rem;
            margin-bottom: 0.6rem;
        ">
            <div style="display:flex; justify-content:space-between;
                        align-items:flex-start; margin-bottom:0.3rem;">
                <span style="font-family:var(--font-mono); font-size:0.72rem;
                             color:#4ade80; font-weight:600; word-break:break-all;">
                    {_safe_html(cited_url[:80])}
                </span>
                <span style="
                    background:{level_bg}; color:{level_color};
                    font-family:var(--font-mono); font-size:0.65rem;
                    font-weight:600; padding:2px 8px; border-radius:999px;
                    white-space:nowrap; margin-left:0.5rem; flex-shrink:0;
                ">{level_label}</span>
            </div>
            <div style="font-family:var(--font-mono); font-size:0.68rem;
                        color:var(--text-secondary); margin-bottom:0.3rem;">
                Prompt: {_safe_html(prompt[:60])}
            </div>
            <div style="font-family:var(--font-body); font-size:0.82rem;
                        color:var(--text-secondary); line-height:1.5;
                        font-style:italic;">
                "{_safe_html(snippet)}"
            </div>
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Phase 2 — Prompt Visibility Row
# ===========================================================================


def render_prompt_row(
    prompt: str,
    visibility: str,
    competitor_url: Optional[str] = None,
    search_position: Optional[int] = None,
) -> None:
    """
    Render a single keyword prompt visibility result row.

    Shows the prompt, a coloured visibility chip, position if found,
    and the competitor URL that ranked instead (if applicable).

    Parameters
    ----------
    prompt : str
    visibility : str  "exact_match" | "brand_visible" | "not_visible"
    competitor_url : Optional[str]
    search_position : Optional[int]
    """
    vis_map = {
        "exact_match":   ("var(--score-green-bg)", "var(--score-green-text)", "Found"),
        "brand_visible": ("var(--score-amber-bg)", "var(--score-amber-text)", "Brand visible"),
        "not_visible":   ("var(--score-red-bg)",   "var(--score-red-text)",   "Not found"),
    }
    chip_bg, chip_fg, chip_label = vis_map.get(
        visibility,
        ("var(--border)", "var(--text-secondary)", visibility),
    )

    position_text = f"  Position: #{search_position}" if search_position else ""
    competitor_html = ""
    if competitor_url and visibility == "not_visible":
        competitor_html = (
            f'<div style="font-size:0.72rem; color:var(--text-secondary); '
            f'font-family:var(--font-mono); margin-top:4px;">'
            f'Ranking instead: {_safe_html(competitor_url[:70])}</div>'
        )

    html = f"""
        <div class="prompt-row">
            <span class="prompt-row-text">{_safe_html(prompt)}</span>
            <span style="
                background:{chip_bg}; color:{chip_fg};
                font-family:var(--font-mono); font-size:0.68rem;
                font-weight:600; padding:2px 10px; border-radius:999px;
                white-space:nowrap;
            ">{chip_label}{position_text}</span>
        </div>
        {competitor_html}
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Phase 2 — Delta Banner
# ===========================================================================


def render_delta_banner(
    cqs_delta: float,
    summary: str,
    improved: list,
    regressed: list,
) -> None:
    """
    Render a compact CQS progress banner for the delta section.

    Shown at the top of results when a previous audit exists for the URL.

    Parameters
    ----------
    cqs_delta : float
    summary : str
    improved : list[str]   metric names that improved
    regressed : list[str]  metric names that regressed
    """
    if cqs_delta > 0:
        delta_class = "delta-positive"
        sign = "+"
        bg = "rgba(22,101,52,0.12)"
        border = "rgba(34,197,94,0.3)"
    elif cqs_delta < 0:
        delta_class = "delta-negative"
        sign = ""
        bg = "rgba(153,27,27,0.12)"
        border = "rgba(248,113,113,0.3)"
    else:
        delta_class = "delta-neutral"
        sign = ""
        bg = "rgba(55,65,81,0.2)"
        border = "var(--border)"

    improved_html = ""
    if improved:
        improved_html = (
            f'<span style="font-size:0.75rem; color:#4ade80; margin-left:0.75rem;">'
            f'Improved: {", ".join(improved[:3])}</span>'
        )

    regressed_html = ""
    if regressed:
        regressed_html = (
            f'<span style="font-size:0.75rem; color:#f87171; margin-left:0.75rem;">'
            f'Regressed: {", ".join(regressed[:3])}</span>'
        )

    html = f"""
        <div style="
            background:    {bg};
            border:        1px solid {border};
            border-radius: var(--radius-md);
            padding:       0.75rem 1.25rem;
            margin-bottom: 1rem;
            display:       flex;
            align-items:   center;
            flex-wrap:     wrap;
            gap:           0.25rem;
        ">
            <span style="font-family:var(--font-heading); font-size:1rem;
                         font-weight:700;" class="{delta_class}">
                {sign}{cqs_delta:.1f} pts
            </span>
            <span style="font-family:var(--font-body); font-size:0.875rem;
                         color:var(--text-secondary); margin-left:0.5rem;">
                {_safe_html(summary)}
            </span>
            {improved_html}
            {regressed_html}
        </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ===========================================================================
# Divider
# ===========================================================================


def render_divider() -> None:
    """Render a subtle styled horizontal rule between dashboard sections."""
    st.markdown(
        '<hr style="border:none; border-top:1px solid var(--border); margin:1.5rem 0;">',
        unsafe_allow_html=True,
    )