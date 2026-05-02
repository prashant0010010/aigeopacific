"""
reports/theme.py
================
Visual design system (design tokens) for AiGeoPacific PDF audit reports.

This module is the visual DNA of the entire report system. Every color,
font, spacing constant, and paragraph style is defined here and referenced
by all other report modules. Changing a value here changes the entire
PDF aesthetic instantly.

Design philosophy: Dark Editorial + Premium SaaS Report
Inspired by: Notion AI reports, Stripe engineering docs, Bloomberg terminal

Safety guarantee: This module NEVER crashes, even if the custom font
directory is missing or completely empty. All styles fall back gracefully
to built-in ReportLab system fonts (Helvetica / Courier).

Import-safe: no side effects on import. Call register_fonts() explicitly
before building any PDF document.

Allowed imports: os, reportlab.pdfbase, reportlab.lib only.
"""

import os

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ===========================================================================
# Color Tokens
# ===========================================================================

# Core palette (dark — kept for legacy compat, not used in PDF)
BG_DARK   = colors.HexColor("#0a0c10")
GOLD      = colors.HexColor("#c49b00")   # darker gold — legible on white
CARD_BG   = colors.HexColor("#f8f9fa")   # light card bg for PDF
BORDER    = colors.HexColor("#e5e7eb")   # light border for PDF
TEXT_MAIN = colors.HexColor("#111827")   # dark text on white PDF
TEXT_DIM  = colors.HexColor("#6b7280")   # muted dark text

# Status palette — PDF light mode uses readable colors on white
SUCCESS = colors.HexColor("#dcfce7")    # light green bg
WARNING = colors.HexColor("#fef3c7")    # light amber bg
ERROR   = colors.HexColor("#fee2e2")    # light red bg

# Status text palette (foreground on status backgrounds)
SUCCESS_TEXT = colors.HexColor("#166534")
WARNING_TEXT = colors.HexColor("#92400e")
ERROR_TEXT   = colors.HexColor("#991b1b")

# PDF-specific light-mode palette (always used in reports)
PDF_BG        = colors.HexColor("#ffffff")   # white page background
PDF_ACCENT    = colors.HexColor("#c49b00")   # gold — readable on white
PDF_CARD_BG   = colors.HexColor("#f8f9fa")   # off-white card
PDF_BORDER    = colors.HexColor("#e5e7eb")   # light border
PDF_TEXT      = colors.HexColor("#111827")   # near-black body text
PDF_TEXT_DIM  = colors.HexColor("#6b7280")   # muted secondary text
PDF_SUCCESS_BG   = colors.HexColor("#dcfce7")
PDF_SUCCESS_TEXT = colors.HexColor("#166534")
PDF_WARNING_BG   = colors.HexColor("#fef3c7")
PDF_WARNING_TEXT = colors.HexColor("#92400e")
PDF_ERROR_BG     = colors.HexColor("#fee2e2")
PDF_ERROR_TEXT   = colors.HexColor("#991b1b")

# Convenience aliases
WHITE = colors.HexColor("#FFFFFF")
BLACK = colors.HexColor("#000000")

# Score band thresholds (used by components and pdf_builder)
SCORE_STRONG_THRESHOLD = 70   # >= 70 → SUCCESS (green)
SCORE_FAIR_THRESHOLD   = 45   # >= 45 → WARNING (amber)
                               # <  45 → ERROR   (red)

# ===========================================================================
# Font Identity
# ===========================================================================

# Logical font keys — always reference fonts through FONT_MAP, never by
# raw string. This guarantees that registration failures are transparent
# to every module that imports theme.py.

_FONT_KEY_HEADING = "Syne-Bold"
_FONT_KEY_BODY    = "DM-Sans"
_FONT_KEY_MONO    = "DM-Mono"

# Fallback fonts are built-in ReportLab / PDF system fonts — always safe.
_FALLBACK_HEADING = "Helvetica-Bold"
_FALLBACK_BODY    = "Helvetica"
_FALLBACK_MONO    = "Courier"

# Global font mapping — mutated by register_fonts() when registration fails.
# All styles MUST reference fonts via this dict, e.g. FONT_MAP["Syne-Bold"].
FONT_MAP: dict = {
    _FONT_KEY_HEADING: _FALLBACK_HEADING,  # default = fallback until registered
    _FONT_KEY_BODY:    _FALLBACK_BODY,
    _FONT_KEY_MONO:    _FALLBACK_MONO,
}

# Convenience accessors — updated by register_fonts() after successful registration
HEADING_FONT: str = FONT_MAP[_FONT_KEY_HEADING]
BODY_FONT:    str = FONT_MAP[_FONT_KEY_BODY]
MONO_FONT:    str = FONT_MAP[_FONT_KEY_MONO]

# ===========================================================================
# Layout Constants
# ===========================================================================

# Page margins: (left, right, top, bottom) in points
PAGE_MARGINS = (40, 40, 40, 40)

# Gap between columns in multi-column layouts
COLUMN_GAP = 16

# Visual border radius token (used by drawing components)
BORDER_RADIUS = 10

# Standard spacing scale (points)
SPACE_XS  = 4
SPACE_SM  = 8
SPACE_MD  = 16
SPACE_LG  = 24
SPACE_XL  = 40

# Rule / divider line weight
RULE_WEIGHT = 0.5

# Progress bar height (points)
PROGRESS_BAR_HEIGHT = 10

# Footer height reserved at bottom of each page
FOOTER_HEIGHT = 32

# Minimum progress bar fill ratio — prevents zero-width rendering crash
# bar_fill = max(MIN_BAR_FILL_RATIO, bar_width * (score / 100))
MIN_BAR_FILL_RATIO = 0.5

# ===========================================================================
# Font Registration
# ===========================================================================

# Font file names relative to the font directory
_FONT_FILES = {
    _FONT_KEY_HEADING: "Syne-Bold.ttf",
    _FONT_KEY_BODY:    "DM-Sans.ttf",
    _FONT_KEY_MONO:    "DM-Mono.ttf",
}


def register_fonts(font_dir: str) -> None:
    """
    Attempt to register custom TTF fonts from the given directory.

    Each font is registered independently inside its own try/except block.
    A failure on one font never prevents the others from being attempted.

    On success: FONT_MAP entry is updated to the custom font name.
    On failure: FONT_MAP entry remains pointing to the safe system fallback,
                a warning is printed, and execution continues normally.

    After registration, the module-level convenience aliases (HEADING_FONT,
    BODY_FONT, MONO_FONT) are updated to reflect the final resolved fonts.

    Parameters
    ----------
    font_dir : str
        Absolute or relative path to the directory containing .ttf files.
        Safe to call even if the directory does not exist.

    Returns
    -------
    None
    """
    global HEADING_FONT, BODY_FONT, MONO_FONT

    # -----------------------------------------------------------------------
    # Syne-Bold (heading)
    # -----------------------------------------------------------------------
    try:
        path = os.path.join(font_dir, _FONT_FILES[_FONT_KEY_HEADING])
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Font file not found: {path}")
        pdfmetrics.registerFont(TTFont(_FONT_KEY_HEADING, path))
        FONT_MAP[_FONT_KEY_HEADING] = _FONT_KEY_HEADING
        print(f"[Theme] Registered font: {_FONT_KEY_HEADING}")
    except Exception as exc:
        print(f"[Theme] Could not register '{_FONT_KEY_HEADING}': {exc} "
              f"— falling back to '{_FALLBACK_HEADING}'")
        FONT_MAP[_FONT_KEY_HEADING] = _FALLBACK_HEADING

    # -----------------------------------------------------------------------
    # DM-Sans (body)
    # -----------------------------------------------------------------------
    try:
        path = os.path.join(font_dir, _FONT_FILES[_FONT_KEY_BODY])
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Font file not found: {path}")
        pdfmetrics.registerFont(TTFont(_FONT_KEY_BODY, path))
        FONT_MAP[_FONT_KEY_BODY] = _FONT_KEY_BODY
        print(f"[Theme] Registered font: {_FONT_KEY_BODY}")
    except Exception as exc:
        print(f"[Theme] Could not register '{_FONT_KEY_BODY}': {exc} "
              f"— falling back to '{_FALLBACK_BODY}'")
        FONT_MAP[_FONT_KEY_BODY] = _FALLBACK_BODY

    # -----------------------------------------------------------------------
    # DM-Mono (monospace / labels)
    # -----------------------------------------------------------------------
    try:
        path = os.path.join(font_dir, _FONT_FILES[_FONT_KEY_MONO])
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Font file not found: {path}")
        pdfmetrics.registerFont(TTFont(_FONT_KEY_MONO, path))
        FONT_MAP[_FONT_KEY_MONO] = _FONT_KEY_MONO
        print(f"[Theme] Registered font: {_FONT_KEY_MONO}")
    except Exception as exc:
        print(f"[Theme] Could not register '{_FONT_KEY_MONO}': {exc} "
              f"— falling back to '{_FALLBACK_MONO}'")
        FONT_MAP[_FONT_KEY_MONO] = _FALLBACK_MONO

    # -----------------------------------------------------------------------
    # Update convenience aliases to reflect resolved fonts
    # -----------------------------------------------------------------------
    HEADING_FONT = FONT_MAP[_FONT_KEY_HEADING]
    BODY_FONT    = FONT_MAP[_FONT_KEY_BODY]
    MONO_FONT    = FONT_MAP[_FONT_KEY_MONO]

    print(f"[Theme] Font resolution complete — "
          f"Heading: {HEADING_FONT} | Body: {BODY_FONT} | Mono: {MONO_FONT}")


# ===========================================================================
# Paragraph Style Factory
# ===========================================================================

def _base_styles() -> object:
    """Return the ReportLab sample stylesheet as a base to extend from."""
    return getSampleStyleSheet()


def build_styles() -> dict:
    """
    Build and return the complete set of paragraph styles for the PDF report.

    All font references go through FONT_MAP so that fallback resolution is
    automatic. Call register_fonts() before build_styles() to ensure the
    mapping reflects successfully registered fonts.

    Returns
    -------
    dict
        Keyed style container. Keys:
        "title", "heading1", "heading2", "body", "body_dim",
        "metric_label", "caption", "callout", "footer", "code"
    """
    return {

        # ------------------------------------------------------------------
        # Display / Cover title
        # ------------------------------------------------------------------
        "title": ParagraphStyle(
            name="AigeoTitle",
            fontName=FONT_MAP[_FONT_KEY_HEADING],
            fontSize=28,
            leading=34,
            textColor=GOLD,
            spaceAfter=SPACE_MD,
            spaceBefore=SPACE_SM,
            alignment=0,   # left-aligned
        ),

        # ------------------------------------------------------------------
        # Section heading (H1 equivalent in report)
        # ------------------------------------------------------------------
        "heading1": ParagraphStyle(
            name="AigeoHeading1",
            fontName=FONT_MAP[_FONT_KEY_HEADING],
            fontSize=16,
            leading=22,
            textColor=GOLD,
            spaceAfter=SPACE_SM,
            spaceBefore=SPACE_MD,
            alignment=0,
        ),

        # ------------------------------------------------------------------
        # Sub-section heading (H2 equivalent)
        # ------------------------------------------------------------------
        "heading2": ParagraphStyle(
            name="AigeoHeading2",
            fontName=FONT_MAP[_FONT_KEY_HEADING],
            fontSize=12,
            leading=18,
            textColor=GOLD,
            spaceAfter=SPACE_XS,
            spaceBefore=SPACE_SM,
            alignment=0,
        ),

        # ------------------------------------------------------------------
        # Standard body text
        # ------------------------------------------------------------------
        "body": ParagraphStyle(
            name="AigeoBody",
            fontName=FONT_MAP[_FONT_KEY_BODY],
            fontSize=9,
            leading=14,
            textColor=TEXT_MAIN,
            spaceAfter=SPACE_SM,
            spaceBefore=0,
            alignment=0,
            wordWrap="LTR",
        ),

        # ------------------------------------------------------------------
        # Dimmed / secondary body text
        # ------------------------------------------------------------------
        "body_dim": ParagraphStyle(
            name="AigeoBodyDim",
            fontName=FONT_MAP[_FONT_KEY_BODY],
            fontSize=9,
            leading=14,
            textColor=TEXT_DIM,
            spaceAfter=SPACE_XS,
            spaceBefore=0,
            alignment=0,
            wordWrap="LTR",
        ),

        # ------------------------------------------------------------------
        # Metric label / monospace tag
        # ------------------------------------------------------------------
        "metric_label": ParagraphStyle(
            name="AigeoMetricLabel",
            fontName=FONT_MAP[_FONT_KEY_MONO],
            fontSize=8,
            leading=12,
            textColor=TEXT_DIM,
            spaceAfter=SPACE_XS,
            spaceBefore=0,
            alignment=0,
        ),

        # ------------------------------------------------------------------
        # Small caption (chart labels, footnotes)
        # ------------------------------------------------------------------
        "caption": ParagraphStyle(
            name="AigeoCaption",
            fontName=FONT_MAP[_FONT_KEY_BODY],
            fontSize=7,
            leading=11,
            textColor=TEXT_DIM,
            spaceAfter=0,
            spaceBefore=0,
            alignment=1,   # centred
        ),

        # ------------------------------------------------------------------
        # Callout / insight box text
        # ------------------------------------------------------------------
        "callout": ParagraphStyle(
            name="AigeoCallout",
            fontName=FONT_MAP[_FONT_KEY_BODY],
            fontSize=9,
            leading=14,
            textColor=GOLD,
            spaceAfter=SPACE_XS,
            spaceBefore=SPACE_XS,
            leftIndent=SPACE_MD,
            borderPadding=(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM),
            alignment=0,
        ),

        # ------------------------------------------------------------------
        # Page footer text
        # ------------------------------------------------------------------
        "footer": ParagraphStyle(
            name="AigeoFooter",
            fontName=FONT_MAP[_FONT_KEY_MONO],
            fontSize=7,
            leading=10,
            textColor=TEXT_DIM,
            spaceAfter=0,
            spaceBefore=0,
            alignment=1,   # centred
        ),

        # ------------------------------------------------------------------
        # Inline code / mono snippet
        # ------------------------------------------------------------------
        "code": ParagraphStyle(
            name="AigeoCode",
            fontName=FONT_MAP[_FONT_KEY_MONO],
            fontSize=8,
            leading=12,
            textColor=TEXT_MAIN,
            spaceAfter=SPACE_XS,
            spaceBefore=SPACE_XS,
            backColor=CARD_BG,
            leftIndent=SPACE_SM,
            rightIndent=SPACE_SM,
            alignment=0,
        ),
    }


# ===========================================================================
# Score → Color Helpers
# ===========================================================================

def score_band_color(score: float) -> colors.HexColor:
    """
    Return the background status color for a given CQS / metric score.

    Bands:
    - score >= 70 → SUCCESS (green)
    - score >= 45 → WARNING (amber)
    - score <  45 → ERROR   (red)

    Parameters
    ----------
    score : float
        Metric or CQS score in the range 0–100.

    Returns
    -------
    colors.HexColor
    """
    if score >= SCORE_STRONG_THRESHOLD:
        return SUCCESS
    elif score >= SCORE_FAIR_THRESHOLD:
        return WARNING
    else:
        return ERROR


def score_band_text_color(score: float) -> colors.HexColor:
    """
    Return the foreground text color appropriate for a score band.

    Parameters
    ----------
    score : float
        Metric or CQS score in the range 0–100.

    Returns
    -------
    colors.HexColor
    """
    if score >= SCORE_STRONG_THRESHOLD:
        return SUCCESS_TEXT
    elif score >= SCORE_FAIR_THRESHOLD:
        return WARNING_TEXT
    else:
        return ERROR_TEXT


def score_band_label(score: float) -> str:
    """
    Return a plain-English band label for a given score.

    Parameters
    ----------
    score : float
        Metric or CQS score in the range 0–100.

    Returns
    -------
    str
        "Strong", "Fair", or "Weak"
    """
    if score >= SCORE_STRONG_THRESHOLD:
        return "Strong"
    elif score >= SCORE_FAIR_THRESHOLD:
        return "Fair"
    else:
        return "Weak"