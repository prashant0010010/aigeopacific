"""
reports/components.py
=====================
Reusable PDF drawing components for the AiGeoPacific AI Citation Analyser.

This module provides modular, canvas-based drawing functions that compose
the visual layout of the audit PDF report. Every component accepts explicit
(x, y) coordinates and never makes assumptions about page position.

Design aesthetic: Dark Editorial Dashboard
  Background: #0a0c10  |  Gold: #f5b800  |  Cards: #141720  |  Border: #374151

All components are safe:
- Missing or None values are handled without crashing
- Zero scores render correctly (minimum bar fill enforced)
- Empty text sections are silently skipped

Import-safe: no side effects. Components only draw when called.

Allowed imports: reportlab stdlib, reports.theme only.
"""

import math
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph

import reports.theme as theme

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_PAD_SM  = theme.SPACE_SM    # 8 pt
_PAD_MD  = theme.SPACE_MD    # 16 pt
_PAD_XS  = theme.SPACE_XS    # 4 pt
_LINE_H  = 13                 # default text line height (points)
_CARD_R  = theme.BORDER_RADIUS


# ===========================================================================
# Low-level drawing helpers
# ===========================================================================

def _draw_rounded_rect(
    canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float,
    fill_color,
    stroke_color=None,
    stroke_width: float = 0.5,
) -> None:
    """
    Draw a filled rounded rectangle on the canvas.

    Parameters
    ----------
    canvas      : ReportLab canvas object
    x, y        : Bottom-left corner (ReportLab coordinate system)
    width       : Rectangle width
    height      : Rectangle height
    radius      : Corner radius
    fill_color  : Fill color (ReportLab color object)
    stroke_color: Border color (None = no border)
    stroke_width: Border line width
    """
    canvas.saveState()
    if stroke_color:
        canvas.setStrokeColor(stroke_color)
        canvas.setLineWidth(stroke_width)
    else:
        canvas.setStrokeColor(colors.transparent)
        canvas.setLineWidth(0)
    canvas.setFillColor(fill_color)
    canvas.roundRect(x, y, width, height, radius, fill=1, stroke=1 if stroke_color else 0)
    canvas.restoreState()


def _draw_text(
    canvas,
    x: float,
    y: float,
    text: str,
    font_name: str,
    font_size: float,
    color,
    align: str = "left",
    max_width: float = 0,
) -> None:
    """
    Draw a single line of text. Truncates with ellipsis if max_width is set.

    Parameters
    ----------
    canvas    : ReportLab canvas
    x, y      : Baseline position
    text      : String to draw
    font_name : Registered font name
    font_size : Font size in points
    color     : ReportLab color
    align     : "left" | "center" | "right"
    max_width : If > 0, truncate text to fit within this width
    """
    if not text:
        return

    canvas.saveState()
    canvas.setFont(font_name, font_size)
    canvas.setFillColor(color)

    if max_width > 0:
        while len(text) > 4:
            w = stringWidth(text, font_name, font_size)
            if w <= max_width:
                break
            text = text[:-2] + "..."

    if align == "center":
        canvas.drawCentredString(x, y, text)
    elif align == "right":
        canvas.drawRightString(x, y, text)
    else:
        canvas.drawString(x, y, text)

    canvas.restoreState()


def _draw_paragraph(
    canvas,
    x: float,
    y_top: float,
    width: float,
    text: str,
    style,
) -> float:
    """
    Draw a wrapped Paragraph and return the height consumed.

    Parameters
    ----------
    canvas  : ReportLab canvas
    x       : Left edge
    y_top   : Top edge (converted to ReportLab bottom-left internally)
    width   : Available width
    text    : Content string (may contain basic HTML tags)
    style   : ParagraphStyle object

    Returns
    -------
    float
        Height consumed by the paragraph (points).
    """
    if not text or not text.strip():
        return 0.0

    # Sanitise: strip raw angle brackets that could break XML parsing
    safe_text = text.replace("&", "&amp;")

    try:
        para = Paragraph(safe_text, style)
        w, h = para.wrap(width, 2000)
        para.drawOn(canvas, x, y_top - h)
        return h
    except Exception:
        # Fall back to plain canvas text on any Paragraph error
        canvas.saveState()
        canvas.setFont(style.fontName, style.fontSize)
        canvas.setFillColor(style.textColor)
        canvas.drawString(x, y_top - style.fontSize, text[:80])
        canvas.restoreState()
        return style.fontSize + 4


def _score_fill_color(score: float):
    """Return GOLD for fill, regardless of band — used in progress bars."""
    return theme.GOLD


# ===========================================================================
# Component 1 — Score Badge
# ===========================================================================

def draw_score_badge(
    canvas,
    x: float,
    y: float,
    score,
    label: str = "Citation Quality Score",
) -> None:
    """
    Draw a circular score badge displaying the CQS or a metric score.

    Color coding:
    - score >= 70  →  SUCCESS (green)
    - score >= 45  →  WARNING (amber)
    - score <  45  →  ERROR   (red)

    The badge renders cleanly even when score is 0 or None.

    Parameters
    ----------
    canvas : ReportLab canvas
    x, y   : Top-left corner of the bounding box
    score  : Numeric score 0-100 (None treated as 0)
    label  : Text displayed below the numeric score
    """
    score = float(score) if score is not None else 0.0
    score = max(0.0, min(100.0, score))

    radius = 38
    cx = x + radius
    # ReportLab y is bottom-up; badge centre
    cy = y - radius

    bg_color   = theme.score_band_color(score)
    text_color = theme.score_band_text_color(score)

    # Outer ring (border)
    canvas.saveState()
    canvas.setStrokeColor(theme.GOLD)
    canvas.setLineWidth(1.5)
    canvas.setFillColor(bg_color)
    canvas.circle(cx, cy, radius, fill=1, stroke=1)
    canvas.restoreState()

    # Score number
    score_str = str(int(round(score)))
    score_font_size = 22 if len(score_str) < 3 else 18
    _draw_text(
        canvas, cx, cy + 4,
        score_str,
        font_name=theme.FONT_MAP[theme._FONT_KEY_HEADING],
        font_size=score_font_size,
        color=text_color,
        align="center",
    )

    # Band label inside badge (small)
    band = theme.score_band_label(score)
    _draw_text(
        canvas, cx, cy - 14,
        band,
        font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
        font_size=7,
        color=text_color,
        align="center",
    )

    # External label below the circle
    _draw_text(
        canvas, cx, cy - radius - 14,
        label,
        font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
        font_size=8,
        color=theme.TEXT_DIM,
        align="center",
        max_width=radius * 2 + 20,
    )


# ===========================================================================
# Component 2 — Progress Bar
# ===========================================================================

def draw_progress_bar(
    canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    score,
    label: str = "",
    show_score: bool = True,
) -> float:
    """
    Draw a horizontal progress bar for a metric score.

    Safety: uses max(MIN_BAR_FILL_RATIO, width * score/100) to prevent
    zero-width rendering crashes when score is 0.

    Parameters
    ----------
    canvas     : ReportLab canvas
    x, y       : Top-left corner of the label / bar block
    width      : Total bar width
    height     : Bar track height
    score      : Numeric score 0-100 (None treated as 0)
    label      : Text displayed above the bar
    show_score : If True, score value is printed to the right of the bar

    Returns
    -------
    float
        Total vertical height consumed (label + bar + padding).
    """
    score = float(score) if score is not None else 0.0
    score = max(0.0, min(100.0, score))

    current_y = y
    label_height = 0

    # Label above the bar
    if label:
        _draw_text(
            canvas, x, current_y - 10,
            label,
            font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
            font_size=8,
            color=theme.TEXT_MAIN,
            max_width=width - 40,
        )
        label_height = 14
        current_y -= label_height

    bar_y = current_y - height  # bottom of bar track (ReportLab bottom-up)

    # Track background
    canvas.saveState()
    canvas.setFillColor(theme.BORDER)
    canvas.setStrokeColor(colors.transparent)
    canvas.roundRect(x, bar_y, width, height, height / 2, fill=1, stroke=0)

    # Score fill — enforced minimum width to avoid zero-width crash
    fill_width = max(theme.MIN_BAR_FILL_RATIO, width * (score / 100))
    fill_color = theme.score_band_color(score)
    canvas.setFillColor(fill_color)
    canvas.roundRect(x, bar_y, fill_width, height, height / 2, fill=1, stroke=0)
    canvas.restoreState()

    # Score value to the right
    if show_score:
        score_str = f"{int(round(score))}"
        _draw_text(
            canvas,
            x + width + _PAD_XS,
            bar_y + 2,
            score_str,
            font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
            font_size=8,
            color=theme.TEXT_DIM,
        )

    total_height = label_height + height + _PAD_XS
    return total_height


# ===========================================================================
# Component 3 — Metric Card
# ===========================================================================

def draw_metric_card(
    canvas,
    x: float,
    y: float,
    width: float,
    metric_score_obj,
) -> float:
    """
    Draw a dashboard-style metric card with score bar and explainability text.

    Accepts a MetricScore Pydantic model (or any object/dict with the
    expected fields). Returns the total height consumed so the caller can
    stack cards vertically.

    Parameters
    ----------
    canvas           : ReportLab canvas
    x, y             : Top-left corner
    width            : Card width
    metric_score_obj : MetricScore model or dict-like with fields:
                       name, score, why_it_matters, how_ai_reads_it, what_to_fix

    Returns
    -------
    float
        Height of the rendered card (points).
    """
    # Normalise input — accept Pydantic model or dict
    def _get(obj, key, default=""):
        if hasattr(obj, key):
            return getattr(obj, key) or default
        if isinstance(obj, dict):
            return obj.get(key) or default
        return default

    name       = _get(metric_score_obj, "name",           "Metric")
    score      = float(_get(metric_score_obj, "score",    0))
    why        = _get(metric_score_obj, "why_it_matters",  "")
    how_ai     = _get(metric_score_obj, "how_ai_reads_it", "")
    what_fix   = _get(metric_score_obj, "what_to_fix",     "")

    score = max(0.0, min(100.0, score))

    # Card padding
    pad   = _PAD_MD
    inner = width - (pad * 2)

    # --- Estimate total card height ---
    # We do a pre-pass to measure paragraph heights
    styles = theme.build_styles()
    body_style  = styles["body"]
    dim_style   = styles["body_dim"]
    label_style = styles["metric_label"]

    def _measure(text, style, w):
        if not text or not text.strip():
            return 0
        try:
            p = Paragraph(text.replace("&", "&amp;"), style)
            _, h = p.wrap(w, 2000)
            return h
        except Exception:
            return style.fontSize + 4

    h_why    = _measure(why,    body_style,  inner)
    h_how    = _measure(how_ai, dim_style,   inner)
    h_fix    = _measure(what_fix, body_style, inner)

    section_gap = 6
    bar_block   = 28   # label + bar
    header_h    = 24   # metric name + score chip row
    bottom_pad  = pad

    card_height = (
        pad + header_h + _PAD_SM
        + bar_block + _PAD_SM
        + (h_why + section_gap if h_why else 0)
        + (h_how + section_gap if h_how else 0)
        + (h_fix + section_gap if h_fix else 0)
        + bottom_pad
    )

    # --- Card background ---
    card_bottom = y - card_height
    _draw_rounded_rect(
        canvas,
        x, card_bottom,
        width, card_height,
        radius=_CARD_R,
        fill_color=theme.CARD_BG,
        stroke_color=theme.BORDER,
        stroke_width=0.5,
    )

    # --- Metric name ---
    cursor = y - pad
    _draw_text(
        canvas, x + pad, cursor - 12,
        name.upper(),
        font_name=theme.FONT_MAP[theme._FONT_KEY_HEADING],
        font_size=9,
        color=theme.GOLD,
        max_width=inner - 60,
    )

    # --- Score chip (top-right of card) ---
    chip_w, chip_h = 46, 16
    chip_x = x + width - pad - chip_w
    chip_y = cursor - chip_h
    chip_color = theme.score_band_color(score)
    _draw_rounded_rect(
        canvas, chip_x, chip_y,
        chip_w, chip_h,
        radius=4,
        fill_color=chip_color,
    )
    chip_label = f"{int(round(score))}  {theme.score_band_label(score)}"
    _draw_text(
        canvas,
        chip_x + chip_w / 2,
        chip_y + 4,
        chip_label,
        font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
        font_size=7,
        color=theme.score_band_text_color(score),
        align="center",
    )

    cursor -= header_h + _PAD_XS

    # --- Progress bar ---
    draw_progress_bar(
        canvas,
        x + pad, cursor,
        inner - 50,
        height=8,
        score=score,
        label="",
        show_score=False,
    )
    cursor -= bar_block

    # --- Divider rule ---
    canvas.saveState()
    canvas.setStrokeColor(theme.BORDER)
    canvas.setLineWidth(theme.RULE_WEIGHT)
    canvas.line(x + pad, cursor, x + width - pad, cursor)
    canvas.restoreState()
    cursor -= _PAD_SM

    # --- Why it matters ---
    if why:
        _draw_text(
            canvas, x + pad, cursor,
            "Why it matters",
            font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
            font_size=7,
            color=theme.GOLD,
        )
        cursor -= 11
        h = _draw_paragraph(canvas, x + pad, cursor, inner, why, body_style)
        cursor -= h + section_gap

    # --- How AI reads it ---
    if how_ai:
        _draw_text(
            canvas, x + pad, cursor,
            "How AI reads it",
            font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
            font_size=7,
            color=theme.TEXT_DIM,
        )
        cursor -= 11
        h = _draw_paragraph(canvas, x + pad, cursor, inner, how_ai, dim_style)
        cursor -= h + section_gap

    # --- What to fix ---
    if what_fix:
        _draw_text(
            canvas, x + pad, cursor,
            "What to fix",
            font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
            font_size=7,
            color=theme.GOLD,
        )
        cursor -= 11
        h = _draw_paragraph(canvas, x + pad, cursor, inner, what_fix, body_style)
        cursor -= h + section_gap

    return card_height


# ===========================================================================
# Component 4 — Competitor Table
# ===========================================================================

def draw_competitor_table(
    canvas,
    x: float,
    y: float,
    width: float,
    comparison_data,
) -> float:
    """
    Draw a side-by-side competitor comparison table.

    Handles 0, 1, 2, or 3 competitors gracefully. If no competitors exist,
    draws a single-row "no data" fallback.

    Parameters
    ----------
    canvas          : ReportLab canvas
    x, y            : Top-left corner
    width           : Available table width
    comparison_data : CompetitorComparison model or dict with:
                      competitors: List[CompetitorMetric]
                      gaps: List[str]

    Returns
    -------
    float
        Total height consumed.
    """
    def _get(obj, key, default=None):
        if hasattr(obj, key):
            return getattr(obj, key) or default
        if isinstance(obj, dict):
            return obj.get(key) or default
        return default

    competitors = _get(comparison_data, "competitors", []) or []
    gaps        = _get(comparison_data, "gaps",        []) or []

    row_h     = 22
    header_h  = 26
    col_url   = width * 0.44
    col_cqs   = width * 0.14
    col_str   = width * 0.42
    pad       = _PAD_SM

    rows = len(competitors) if competitors else 1
    gap_rows = min(len(gaps), 4)
    table_h = header_h + rows * row_h + gap_rows * 18 + _PAD_MD * 2

    cursor = y

    # --- Table background card ---
    _draw_rounded_rect(
        canvas, x, y - table_h,
        width, table_h,
        radius=_CARD_R,
        fill_color=theme.CARD_BG,
        stroke_color=theme.BORDER,
        stroke_width=0.5,
    )

    # --- Header row ---
    header_bg_bottom = y - header_h
    _draw_rounded_rect(
        canvas, x, header_bg_bottom,
        width, header_h,
        radius=0,
        fill_color=theme.BORDER,
    )

    # Round only the top corners of the header
    _draw_rounded_rect(
        canvas, x, header_bg_bottom,
        width, header_h + _CARD_R,
        radius=_CARD_R,
        fill_color=theme.BORDER,
    )

    header_text_y = cursor - 17

    _draw_text(canvas, x + pad, header_text_y, "COMPETITOR URL",
               theme.FONT_MAP[theme._FONT_KEY_MONO], 7, theme.GOLD)
    _draw_text(canvas, x + col_url + pad, header_text_y, "CQS",
               theme.FONT_MAP[theme._FONT_KEY_MONO], 7, theme.GOLD)
    _draw_text(canvas, x + col_url + col_cqs + pad, header_text_y, "STRENGTH",
               theme.FONT_MAP[theme._FONT_KEY_MONO], 7, theme.GOLD)

    cursor -= header_h

    # --- Data rows ---
    if not competitors:
        _draw_text(
            canvas, x + pad, cursor - 14,
            "No competitor data available for this audit.",
            font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
            font_size=8,
            color=theme.TEXT_DIM,
        )
        cursor -= row_h
    else:
        for i, comp in enumerate(competitors):
            row_color = theme.CARD_BG if i % 2 == 0 else colors.HexColor("#1a1f2e")
            row_bottom = cursor - row_h
            canvas.saveState()
            canvas.setFillColor(row_color)
            canvas.setStrokeColor(colors.transparent)
            canvas.rect(x, row_bottom, width, row_h, fill=1, stroke=0)
            canvas.restoreState()

            comp_url = _get(comp, "competitor_url", "Unknown") or "Unknown"
            comp_cqs = float(_get(comp, "cqs", 0) or 0)
            strength = theme.score_band_label(comp_cqs)

            text_y = cursor - 14

            # URL — truncate cleanly
            _draw_text(
                canvas, x + pad, text_y,
                comp_url,
                font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
                font_size=8,
                color=theme.TEXT_MAIN,
                max_width=col_url - pad * 2,
            )

            # CQS score with color
            cqs_color = theme.score_band_color(comp_cqs)
            canvas.saveState()
            canvas.setFillColor(cqs_color)
            canvas.setStrokeColor(colors.transparent)
            canvas.roundRect(x + col_url + pad, cursor - row_h + 4, 32, 14, 3, fill=1, stroke=0)
            canvas.restoreState()
            _draw_text(
                canvas,
                x + col_url + pad + 16, cursor - row_h + 7,
                str(int(round(comp_cqs))),
                font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
                font_size=8,
                color=theme.score_band_text_color(comp_cqs),
                align="center",
            )

            # Strength label
            _draw_text(
                canvas,
                x + col_url + col_cqs + pad, text_y,
                strength,
                font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
                font_size=8,
                color=theme.score_band_text_color(comp_cqs),
                max_width=col_str - pad,
            )

            # Row separator
            canvas.saveState()
            canvas.setStrokeColor(theme.BORDER)
            canvas.setLineWidth(0.3)
            canvas.line(x, row_bottom, x + width, row_bottom)
            canvas.restoreState()

            cursor -= row_h

    # --- Gap insights ---
    if gaps:
        cursor -= _PAD_SM
        _draw_text(
            canvas, x + pad, cursor - 10,
            "KEY INSIGHTS",
            font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
            font_size=7,
            color=theme.GOLD,
        )
        cursor -= 16

        styles = theme.build_styles()
        for gap in gaps[:4]:
            if not gap:
                continue
            # Bullet prefix
            _draw_text(canvas, x + pad, cursor - 2, "1.",
                       theme.FONT_MAP[theme._FONT_KEY_MONO], 7, theme.GOLD)
            h = _draw_paragraph(
                canvas, x + pad + 14, cursor,
                width - pad * 2 - 14, gap, styles["body_dim"]
            )
            cursor -= max(h, 14) + 4

    total_consumed = y - (cursor - _PAD_XS)
    return total_consumed


# ===========================================================================
# Component 5 — Header & Footer
# ===========================================================================

def draw_header_footer(
    canvas,
    page_num: int,
    url: str,
    page_width: float  = 595.27,   # A4 default
    page_height: float = 841.89,
    total_pages: int   = 0,
) -> None:
    """
    Draw the AiGeoPacific branded header and footer on the current page.

    Header: report title (left) + gold rule below
    Footer: brand name (left) | URL (center) | page number (right)

    Parameters
    ----------
    canvas       : ReportLab canvas
    page_num     : Current page number (1-based)
    url          : Audited page URL shown in footer
    page_width   : Canvas page width (points)
    page_height  : Canvas page height (points)
    total_pages  : Total page count for "X of Y" display (0 = omit)
    """
    margin = theme.PAGE_MARGINS[0]   # left/right margin
    usable = page_width - margin * 2

    canvas.saveState()

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    header_y = page_height - 28

    _draw_text(
        canvas,
        margin, header_y,
        "AiGeoPacific",
        font_name=theme.FONT_MAP[theme._FONT_KEY_HEADING],
        font_size=9,
        color=theme.GOLD,
    )
    _draw_text(
        canvas,
        margin + 82, header_y,
        "AI Citation Audit",
        font_name=theme.FONT_MAP[theme._FONT_KEY_BODY],
        font_size=9,
        color=theme.TEXT_DIM,
    )

    # Confidential tag (right-aligned)
    _draw_text(
        canvas,
        page_width - margin, header_y,
        "CONFIDENTIAL",
        font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
        font_size=7,
        color=theme.TEXT_DIM,
        align="right",
    )

    # Gold rule below header
    rule_y = header_y - 10
    canvas.setStrokeColor(theme.GOLD)
    canvas.setLineWidth(0.8)
    canvas.line(margin, rule_y, page_width - margin, rule_y)

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------
    footer_y = 22

    # Subtle rule above footer
    canvas.setStrokeColor(theme.BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(margin, footer_y + 12, page_width - margin, footer_y + 12)

    # Left: brand
    _draw_text(
        canvas, margin, footer_y,
        "AiGeoPacific | Confidential Audit Report",
        font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
        font_size=7,
        color=theme.TEXT_DIM,
    )

    # Center: URL (truncated)
    _draw_text(
        canvas,
        page_width / 2, footer_y,
        url,
        font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
        font_size=7,
        color=theme.TEXT_DIM,
        align="center",
        max_width=usable * 0.45,
    )

    # Right: page number
    page_label = (
        f"Page {page_num} of {total_pages}"
        if total_pages > 0
        else f"Page {page_num}"
    )
    _draw_text(
        canvas, page_width - margin, footer_y,
        page_label,
        font_name=theme.FONT_MAP[theme._FONT_KEY_MONO],
        font_size=7,
        color=theme.TEXT_DIM,
        align="right",
    )

    canvas.restoreState()


# ===========================================================================
# Bonus Component — Section Divider
# ===========================================================================

def draw_section_divider(
    canvas,
    x: float,
    y: float,
    width: float,
    title: str,
) -> float:
    """
    Draw a gold-accented section divider with a heading label.

    Used between major report sections to create visual hierarchy.

    Parameters
    ----------
    canvas : ReportLab canvas
    x, y   : Top-left position
    width  : Available width
    title  : Section heading text

    Returns
    -------
    float
        Height consumed (points).
    """
    canvas.saveState()

    # Gold left accent bar
    canvas.setFillColor(theme.GOLD)
    canvas.setStrokeColor(colors.transparent)
    canvas.rect(x, y - 18, 3, 16, fill=1, stroke=0)

    # Section title
    _draw_text(
        canvas, x + 10, y - 13,
        title.upper(),
        font_name=theme.FONT_MAP[theme._FONT_KEY_HEADING],
        font_size=10,
        color=theme.GOLD,
    )

    # Faint rule extending to right edge
    canvas.setStrokeColor(theme.BORDER)
    canvas.setLineWidth(0.4)
    text_w = stringWidth(title.upper(), theme.FONT_MAP[theme._FONT_KEY_HEADING], 10)
    canvas.line(x + 14 + text_w, y - 6, x + width, y - 6)

    canvas.restoreState()

    return 24   # fixed height consumed


# ===========================================================================
# Bonus Component — Quick Win Card
# ===========================================================================

def draw_quick_win_card(
    canvas,
    x: float,
    y: float,
    width: float,
    items: List[str],
    title: str = "Quick Wins",
) -> float:
    """
    Draw a compact card listing high-priority action items.

    Used in the Executive Summary and Priority Fix Plan sections.

    Parameters
    ----------
    canvas : ReportLab canvas
    x, y   : Top-left corner
    width  : Card width
    items  : List of action strings (max 5 shown)
    title  : Card header text

    Returns
    -------
    float
        Height consumed.
    """
    if not items:
        return 0.0

    items = [i for i in items if i][:5]
    pad   = _PAD_MD
    inner = width - pad * 2
    styles = theme.build_styles()

    # Measure item heights
    item_heights = []
    for item in items:
        try:
            p = Paragraph(item.replace("&", "&amp;"), styles["body"])
            _, h = p.wrap(inner - 20, 2000)
            item_heights.append(max(h, 14))
        except Exception:
            item_heights.append(14)

    total_items_h = sum(item_heights) + len(items) * _PAD_XS
    card_h = pad + 20 + _PAD_SM + total_items_h + pad

    # Card background
    _draw_rounded_rect(
        canvas, x, y - card_h,
        width, card_h,
        radius=_CARD_R,
        fill_color=theme.CARD_BG,
        stroke_color=theme.GOLD,
        stroke_width=0.8,
    )

    cursor = y - pad

    # Title
    _draw_text(
        canvas, x + pad, cursor - 12,
        title.upper(),
        font_name=theme.FONT_MAP[theme._FONT_KEY_HEADING],
        font_size=9,
        color=theme.GOLD,
    )
    cursor -= 20 + _PAD_XS

    # Items with numbered bullets
    for idx, (item, ih) in enumerate(zip(items, item_heights), start=1):
        # Number bubble
        bubble_x = x + pad
        bubble_y = cursor - ih / 2 - 5
        canvas.saveState()
        canvas.setFillColor(theme.GOLD)
        canvas.circle(bubble_x + 6, bubble_y, 6, fill=1, stroke=0)
        canvas.setFillColor(theme.BLACK)
        canvas.setFont(theme.FONT_MAP[theme._FONT_KEY_MONO], 7)
        canvas.drawCentredString(bubble_x + 6, bubble_y - 3, str(idx))
        canvas.restoreState()

        # Item text
        _draw_paragraph(
            canvas, x + pad + 16, cursor,
            inner - 16, item, styles["body"]
        )
        cursor -= ih + _PAD_XS

    return card_h