"""
reports/pdf_builder.py
======================
PDF report orchestrator for the AiGeoPacific AI Citation Analyser.

Phase 2 additions:
- build_bytes(): returns io.BytesIO buffer — wired to st.download_button
- BrandingConfig: white-label support (firm name, accent colour, logo)
- _draw_delta_section(): "Progress Since Last Audit" (conditional)
- _draw_citation_section(): "AI Citations Detected" (conditional, only when found)
- _draw_prompt_visibility(): "Prompt Visibility Analysis" (conditional)
- Phase 2 section order: Cover / Delta? / Executive / Citations? / Visibility /
  Prompts? / Competitor / Metrics / Fix Plan / Appendix

This module never crashes on missing data — every section handles
None/empty inputs and skips gracefully.
"""

import io
from datetime import datetime
from typing import IO, List, Optional, Union

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from core.models import AuditResult
from reports.components import (
    draw_competitor_table,
    draw_header_footer,
    draw_metric_card,
    draw_progress_bar,
    draw_quick_win_card,
    draw_score_badge,
    draw_section_divider,
)
from reports.theme import (
    BORDER,
    CARD_BG,
    FONT_MAP,
    GOLD,
    PAGE_MARGINS,
    RULE_WEIGHT,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    TEXT_DIM,
    TEXT_MAIN,
    build_styles,
    score_band_color,
    score_band_label,
    score_band_text_color,
    _FONT_KEY_BODY,
    _FONT_KEY_HEADING,
    _FONT_KEY_MONO,
)

# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN_L = PAGE_MARGINS[0]
MARGIN_R = PAGE_MARGINS[1]
MARGIN_T = PAGE_MARGINS[2]
MARGIN_B = PAGE_MARGINS[3]

HEADER_RESERVE = 36
FOOTER_RESERVE = 32

CONTENT_TOP    = PAGE_HEIGHT - MARGIN_T - HEADER_RESERVE
CONTENT_BOTTOM = MARGIN_B + FOOTER_RESERVE
CONTENT_WIDTH  = PAGE_WIDTH - MARGIN_L - MARGIN_R


# ===========================================================================
# Phase 2 — BrandingConfig
# ===========================================================================


class BrandingConfig:
    """
    White-label branding settings for the PDF report.

    All fields have safe defaults so the report renders correctly
    without any customisation (AiGeoPacific branding preserved).

    Parameters
    ----------
    firm_name : str
        Name shown in the header wordmark and footer. Default: "AiGeoPacific"
    primary_color : str
        Hex accent colour replacing GOLD in headers and chips.
        Default: "#f5b800"
    logo_path : Optional[str]
        Absolute path to a PNG or JPG logo (max 200x60px display).
        If None or file missing, no logo is drawn.
    footer_text : str
        Text on the right side of the cover footer.
        Default: "Confidential — AiGeoPacific"
    """

    def __init__(
        self,
        firm_name: str = "AiGeoPacific",
        primary_color: str = "#f5b800",
        logo_path: Optional[str] = None,
        footer_text: str = "Confidential — AiGeoPacific",
    ) -> None:
        self.firm_name = firm_name or "AiGeoPacific"
        self.footer_text = footer_text or f"Confidential — {self.firm_name}"
        self.logo_path = logo_path

        # Parse hex to ReportLab color — fallback to GOLD on parse error
        try:
            from reportlab.lib.colors import HexColor
            hex_str = primary_color.strip().lstrip("#")
            if len(hex_str) == 6:
                self.accent_color = HexColor(f"#{hex_str}")
            else:
                self.accent_color = GOLD
        except Exception:
            self.accent_color = GOLD


# ===========================================================================
# PDFBuilder
# ===========================================================================


class PDFBuilder:
    """
    Orchestrates the assembly of the full AiGeoPacific audit PDF.

    Phase 2: accepts optional BrandingConfig for white-label support.
    Adds build_bytes() method that returns io.BytesIO — the output
    wired directly to Streamlit's st.download_button().

    Parameters
    ----------
    audit_result : AuditResult
    output : str or file-like, optional
        If None, build_bytes() must be used.
    branding : BrandingConfig, optional
        White-label branding. Defaults to AiGeoPacific branding.
    """

    def __init__(
        self,
        audit_result: AuditResult,
        output: Union[str, IO, None] = None,
        branding: Optional[BrandingConfig] = None,
    ) -> None:
        self.result    = audit_result
        self.output    = output
        self.branding  = branding or BrandingConfig()
        self.canvas    = None
        self.page_num  = 0
        self.current_y = CONTENT_TOP
        self._styles   = build_styles()

        # Convenience shortcuts
        self.url         = getattr(audit_result, "url", "")
        self.cqs         = float(getattr(audit_result, "cqs", 0) or 0)
        self.metrics     = getattr(audit_result, "metrics", []) or []
        self.enrichment  = getattr(audit_result, "enrichment", None)
        self.search_pres = getattr(audit_result, "search_presence", None)
        self.competitor  = getattr(audit_result, "competitor_comparison", None)
        self.confidence  = getattr(audit_result, "confidence", None)
        self.delta       = getattr(audit_result, "delta", None)
        self.citations   = getattr(audit_result, "citation_check", None)
        self.prompts     = getattr(audit_result, "prompt_presence", []) or []

        # Use branding accent colour for all gold references
        self._accent = self.branding.accent_color

    # -----------------------------------------------------------------------
    # Public entry points
    # -----------------------------------------------------------------------

    def build(self) -> None:
        """Assemble the PDF and write to self.output (file path or buffer)."""
        if self.output is None:
            raise ValueError("output must be set when using build(). Use build_bytes() instead.")
        self._assemble(self.output)

    def build_bytes(self) -> bytes:
        """
        Assemble the PDF and return it as bytes.

        This is the Phase 2 primary method — the bytes are passed directly
        to st.download_button() in app.py.

        Returns
        -------
        bytes
            Complete PDF file as a bytes object.
        """
        buffer = io.BytesIO()
        self._assemble(buffer)
        return buffer.getvalue()

    def _assemble(self, output_target) -> None:
        """Core assembly logic shared by build() and build_bytes()."""
        self.canvas = rl_canvas.Canvas(output_target, pagesize=A4)
        self.canvas.setTitle(f"{self.branding.firm_name} AI Citation Audit Report")
        self.canvas.setAuthor(self.branding.firm_name)
        self.canvas.setSubject(f"AI Citation Audit: {self.url}")

        self._draw_cover_page()

        # Phase 2 section order
        # Section 2 — conditional: only if delta exists
        if self.delta:
            self._draw_delta_section()

        self._draw_executive_summary()

        # Section 4 — conditional: only if citations found
        citation_events = []
        if self.citations:
            citation_events = getattr(self.citations, "citations_found", []) or []
        if citation_events:
            self._draw_citation_section()

        self._draw_visibility_score()

        # Section 6 — conditional: only if prompts were tested
        if self.prompts:
            self._draw_prompt_visibility()

        self._draw_competitor_comparison()
        self._draw_metric_breakdown()
        self._draw_priority_fix_plan()
        self._draw_appendix()

        self.canvas.save()

    # -----------------------------------------------------------------------
    # Pagination helpers
    # -----------------------------------------------------------------------

    def _new_page(self) -> None:
        self.canvas.showPage()
        self.page_num += 1
        self.current_y = CONTENT_TOP
        self._draw_page_chrome()

    def _draw_page_chrome(self) -> None:
        draw_header_footer(
            self.canvas,
            page_num=self.page_num,
            url=self.url,
            page_width=PAGE_WIDTH,
            page_height=PAGE_HEIGHT,
        )

    def _check_page_break(self, required_height: float, buffer: float = 10) -> None:
        if self.current_y - required_height < CONTENT_BOTTOM + buffer:
            self._new_page()

    def _advance(self, points: float) -> None:
        self.current_y -= points

    # -----------------------------------------------------------------------
    # Low-level helpers
    # -----------------------------------------------------------------------

    def _draw_text(
        self,
        text: str,
        font_key: str,
        size: float,
        color,
        x: Optional[float] = None,
        align: str = "left",
        max_width: float = 0,
    ) -> None:
        if not text:
            return
        x = x if x is not None else MARGIN_L
        self.canvas.saveState()
        self.canvas.setFont(FONT_MAP[font_key], size)
        self.canvas.setFillColor(color)
        if align == "center":
            self.canvas.drawCentredString(x, self.current_y, text)
        elif align == "right":
            self.canvas.drawRightString(x, self.current_y, text)
        else:
            self.canvas.drawString(x, self.current_y, text)
        self.canvas.restoreState()

    def _draw_paragraph(
        self,
        text: str,
        style_key: str,
        x: Optional[float] = None,
        width: Optional[float] = None,
        advance: bool = True,
    ) -> float:
        if not text or not text.strip():
            return 0.0
        from reportlab.platypus import Paragraph as Para
        x = x if x is not None else MARGIN_L
        width = width if width is not None else CONTENT_WIDTH
        style = self._styles[style_key]
        safe = text.replace("&", "&amp;")
        try:
            p = Para(safe, style)
            w, h = p.wrap(width, 2000)
            p.drawOn(self.canvas, x, self.current_y - h)
            if advance:
                self._advance(h + SPACE_XS)
            return h
        except Exception:
            self.canvas.setFont(style.fontName, style.fontSize)
            self.canvas.setFillColor(style.textColor)
            self.canvas.drawString(x, self.current_y, text[:100])
            if advance:
                self._advance(style.fontSize + SPACE_XS)
            return style.fontSize

    def _rule(self, color=None, weight: float = RULE_WEIGHT) -> None:
        color = color or BORDER
        self.canvas.saveState()
        self.canvas.setStrokeColor(color)
        self.canvas.setLineWidth(weight)
        self.canvas.line(MARGIN_L, self.current_y, MARGIN_L + CONTENT_WIDTH, self.current_y)
        self.canvas.restoreState()

    def _fill_dark_background(self) -> None:
        from reports.theme import BG_DARK
        self.canvas.saveState()
        self.canvas.setFillColor(BG_DARK)
        self.canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        self.canvas.restoreState()

    # -----------------------------------------------------------------------
    # Logo helper (Phase 2)
    # -----------------------------------------------------------------------

    def _draw_logo(self, x: float, y: float, max_w: float = 200, max_h: float = 60) -> None:
        """
        Draw the client logo on the cover page if a logo_path is configured.

        Silently skips if the file is missing or cannot be read.
        """
        logo_path = self.branding.logo_path
        if not logo_path:
            return
        try:
            import os
            if not os.path.exists(logo_path):
                return
            self.canvas.saveState()
            self.canvas.drawImage(
                logo_path,
                x=x,
                y=y,
                width=max_w,
                height=max_h,
                preserveAspectRatio=True,
                anchor="ne",
                mask="auto",
            )
            self.canvas.restoreState()
        except Exception:
            pass  # Never crash on missing/corrupt logo

    # =======================================================================
    # Section 1 — Cover Page
    # =======================================================================

    def _draw_cover_page(self) -> None:
        self.page_num = 1
        self._fill_dark_background()

        c = self.canvas

        # Accent top bar (uses branding colour)
        c.saveState()
        c.setFillColor(self._accent)
        c.rect(0, PAGE_HEIGHT - 6, PAGE_WIDTH, 6, fill=1, stroke=0)
        c.restoreState()

        # Brand wordmark (uses firm_name from branding)
        cy = PAGE_HEIGHT - 60
        c.saveState()
        c.setFont(FONT_MAP[_FONT_KEY_HEADING], 11)
        c.setFillColor(self._accent)
        c.drawString(MARGIN_L, cy, self.branding.firm_name)
        c.setFont(FONT_MAP[_FONT_KEY_BODY], 11)
        c.setFillColor(TEXT_DIM)
        c.drawString(MARGIN_L + len(self.branding.firm_name) * 6.5 + 8, cy, "AI Citation Analyzer")
        c.restoreState()

        # Client logo (top-right — Phase 2)
        self._draw_logo(
            x=PAGE_WIDTH - MARGIN_R - 200,
            y=PAGE_HEIGHT - 80,
            max_w=180,
            max_h=50,
        )

        # Rule below wordmark
        cy -= 14
        c.saveState()
        c.setStrokeColor(self._accent)
        c.setLineWidth(0.8)
        c.line(MARGIN_L, cy, PAGE_WIDTH - MARGIN_R, cy)
        c.restoreState()

        # Report title block
        cy -= 60
        c.saveState()
        c.setFont(FONT_MAP[_FONT_KEY_HEADING], 26)
        c.setFillColor(TEXT_MAIN)
        c.drawString(MARGIN_L, cy, "AI Citation")
        cy -= 34
        c.setFillColor(self._accent)
        c.drawString(MARGIN_L, cy, "Audit Report")
        c.restoreState()

        # URL label
        cy -= 28
        c.saveState()
        c.setFont(FONT_MAP[_FONT_KEY_MONO], 8)
        c.setFillColor(TEXT_DIM)
        c.drawString(MARGIN_L, cy, "ANALYZED URL")
        cy -= 14
        c.setFont(FONT_MAP[_FONT_KEY_BODY], 9)
        c.setFillColor(TEXT_MAIN)
        display_url = self.url[:80] + ("..." if len(self.url) > 80 else "")
        c.drawString(MARGIN_L, cy, display_url)
        c.restoreState()

        # CQS badge
        badge_cx = PAGE_WIDTH / 2
        badge_y = cy - 80
        draw_score_badge(c, x=badge_cx - 38, y=badge_y, score=self.cqs, label="Citation Quality Score")

        band = score_band_label(self.cqs)
        interp_y = badge_y - 100
        c.saveState()
        c.setFont(FONT_MAP[_FONT_KEY_BODY], 9)
        c.setFillColor(TEXT_DIM)
        c.drawCentredString(badge_cx, interp_y, f"This page is a {band} AI citation candidate")
        c.restoreState()

        # Confidence chip
        if self.confidence:
            conf_level = getattr(self.confidence, "level", "Low")
            chip_colors = {"High": self._accent, "Medium": TEXT_DIM, "Low": BORDER}
            chip_color = chip_colors.get(conf_level, BORDER)
            chip_x = badge_cx - 45
            chip_y = interp_y - 24
            c.saveState()
            c.setFillColor(chip_color)
            c.roundRect(chip_x, chip_y, 90, 16, 4, fill=1, stroke=0)
            c.setFont(FONT_MAP[_FONT_KEY_MONO], 8)
            c.setFillColor(TEXT_MAIN)
            c.drawCentredString(badge_cx, chip_y + 4, f"Confidence: {conf_level}")
            c.restoreState()

        # Date footer
        date_str = datetime.now().strftime("%B %d, %Y")
        c.saveState()
        c.setFont(FONT_MAP[_FONT_KEY_MONO], 7)
        c.setFillColor(TEXT_DIM)
        c.drawString(MARGIN_L, 40, f"Report generated: {date_str}")
        c.drawRightString(PAGE_WIDTH - MARGIN_R, 40, self.branding.footer_text)
        c.restoreState()

        # Accent bottom bar
        c.saveState()
        c.setFillColor(self._accent)
        c.rect(0, 0, PAGE_WIDTH, 4, fill=1, stroke=0)
        c.restoreState()

        c.showPage()
        self.page_num = 2
        self.current_y = CONTENT_TOP
        self._draw_page_chrome()

    # =======================================================================
    # Phase 2 — Section 2 (conditional): Progress Since Last Audit
    # =======================================================================

    def _draw_delta_section(self) -> None:
        """
        Render CQS progress comparison. Shown ONLY when self.delta is set.
        """
        if not self.delta:
            return

        self._check_page_break(120)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH,
            "Progress Since Last Audit"
        )
        self._advance(h + SPACE_SM)

        cqs_delta = float(getattr(self.delta, "cqs_delta", 0.0) or 0.0)
        summary = getattr(self.delta, "summary", "") or ""
        improved = getattr(self.delta, "improved_metrics", []) or []
        regressed = getattr(self.delta, "regressed_metrics", []) or []

        # CQS delta headline
        sign = "+" if cqs_delta > 0 else ""
        self._check_page_break(30)
        self._draw_text(f"CQS Change: {sign}{cqs_delta:.1f} points", _FONT_KEY_HEADING, 11, self._accent)
        self._advance(16)

        if summary:
            self._draw_paragraph(summary, "body_dim", advance=True)
            self._advance(SPACE_XS)

        if improved:
            self._check_page_break(20)
            self._draw_text(f"Improved: {', '.join(improved[:5])}", _FONT_KEY_MONO, 8, TEXT_DIM)
            self._advance(14)

        if regressed:
            self._check_page_break(20)
            self._draw_text(f"Regressed: {', '.join(regressed[:5])}", _FONT_KEY_MONO, 8, BORDER)
            self._advance(14)

        self._advance(SPACE_MD)

    # =======================================================================
    # Section 3 — Executive Summary
    # =======================================================================

    def _draw_executive_summary(self) -> None:
        self._check_page_break(120)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, "Executive Summary"
        )
        self._advance(h + SPACE_SM)

        summary = getattr(self.result, "audit_summary", "") or ""
        if summary:
            self._draw_paragraph(summary, "body_dim", advance=True)
            self._advance(SPACE_SM)

        if self.enrichment:
            impact = getattr(self.enrichment, "business_impact", "") or ""
            if impact:
                self._check_page_break(60)
                self._draw_text("Business Impact", _FONT_KEY_MONO, 8, self._accent)
                self._advance(14)
                self._draw_paragraph(impact, "body", advance=True)
                self._advance(SPACE_SM)

        quick_wins = []
        if self.enrichment:
            quick_wins = getattr(self.enrichment, "quick_wins", []) or []

        if quick_wins:
            self._check_page_break(100)
            card_h = draw_quick_win_card(
                self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, quick_wins,
                title="Quick Wins",
            )
            self._advance(card_h + SPACE_MD)

        self._advance(SPACE_SM)

    # =======================================================================
    # Phase 2 — Section 4 (conditional): AI Citations Detected
    # =======================================================================

    def _draw_citation_section(self) -> None:
        """
        Render AI citations. Shown ONLY when citations_found is non-empty.
        """
        if not self.citations:
            return

        citation_events = getattr(self.citations, "citations_found", []) or []
        if not citation_events:
            return

        self._check_page_break(120)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH,
            "AI Citations Detected"
        )
        self._advance(h + SPACE_SM)

        count = len(citation_events)
        checked = getattr(self.citations, "checked_prompts", 0)
        self._draw_text(
            f"{count} citation(s) found across {checked} prompts",
            _FONT_KEY_MONO, 8, self._accent
        )
        self._advance(14)

        for event in citation_events:
            self._check_page_break(60)
            cited_url = getattr(event, "cited_url", "") or ""
            level = getattr(event, "citation_level", "domain")
            prompt = getattr(event, "prompt", "") or ""
            snippet = getattr(event, "context_snippet", "") or ""

            level_label = "Exact page" if level == "page" else "Domain match"
            self._draw_text(
                f"{level_label}: {cited_url[:70]}",
                _FONT_KEY_BODY, 8, TEXT_MAIN
            )
            self._advance(12)

            if prompt:
                self._draw_text(f"Prompt: {prompt[:60]}", _FONT_KEY_MONO, 7, TEXT_DIM)
                self._advance(11)

            if snippet:
                self._draw_paragraph(f'"{snippet}"', "body_dim", advance=True)

            self._rule()
            self._advance(SPACE_XS)

        confidence_note = getattr(self.citations, "confidence_note", "") or ""
        if confidence_note:
            self._check_page_break(30)
            self._draw_paragraph(confidence_note, "body_dim", advance=True)

        self._advance(SPACE_MD)

    # =======================================================================
    # Section 5 — Visibility Score
    # =======================================================================

    def _draw_visibility_score(self) -> None:
        self._check_page_break(160)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, "Visibility Score"
        )
        self._advance(h + SPACE_SM)

        self._check_page_break(90)
        draw_score_badge(
            self.canvas, x=MARGIN_L, y=self.current_y,
            score=self.cqs, label="Citation Quality Score (CQS)",
        )

        cqs_text_x = MARGIN_L + 100
        cqs_text_w = CONTENT_WIDTH - 100

        self.canvas.saveState()
        self.canvas.setFont(FONT_MAP[_FONT_KEY_HEADING], 11)
        self.canvas.setFillColor(self._accent)
        self.canvas.drawString(cqs_text_x, self.current_y - 14, f"Score: {self.cqs:.1f} / 100")
        self.canvas.restoreState()

        self.canvas.saveState()
        self.canvas.setFont(FONT_MAP[_FONT_KEY_BODY], 9)
        self.canvas.setFillColor(TEXT_DIM)
        band = score_band_label(self.cqs)
        self.canvas.drawString(cqs_text_x, self.current_y - 30, f"Band: {band}")
        self.canvas.restoreState()

        interp = {
            "Strong": "This page shows strong AI citation signals.",
            "Fair":   "This page has moderate AI citation visibility.",
            "Weak":   "This page needs significant improvement to attract AI citations.",
        }.get(band, "")

        if interp:
            from reportlab.platypus import Paragraph as Para
            style = self._styles["body_dim"]
            try:
                p = Para(interp, style)
                _, h2 = p.wrap(cqs_text_w, 200)
                p.drawOn(self.canvas, cqs_text_x, self.current_y - 50)
            except Exception:
                pass

        self._advance(100)

        if self.search_pres:
            self._check_page_break(50)
            self._rule()
            self._advance(SPACE_SM)
            self._draw_text("Search Presence", _FONT_KEY_MONO, 8, self._accent)
            self._advance(14)

            sp_status = getattr(self.search_pres, "status", "not_visible")
            sp_score = float(getattr(self.search_pres, "score", 0) or 0)
            sp_found = getattr(self.search_pres, "found_url", None) or ""
            sp_label = sp_status.replace("_", " ").title()

            draw_progress_bar(
                self.canvas, MARGIN_L, self.current_y,
                CONTENT_WIDTH * 0.6, 10,
                score=sp_score, label=f"Status: {sp_label}", show_score=True,
            )
            self._advance(30)

            if sp_found:
                self._draw_text(f"Matched: {sp_found[:70]}", _FONT_KEY_MONO, 7, TEXT_DIM)
                self._advance(12)

        if self.confidence:
            self._check_page_break(50)
            self._rule()
            self._advance(SPACE_SM)
            self._draw_text("Audit Confidence", _FONT_KEY_MONO, 8, self._accent)
            self._advance(14)

            conf_level = getattr(self.confidence, "level", "Low")
            conf_reason = getattr(self.confidence, "reasoning", "") or ""

            self._draw_text(f"Level: {conf_level}", _FONT_KEY_BODY, 9, TEXT_MAIN)
            self._advance(14)

            if conf_reason:
                self._draw_paragraph(conf_reason, "body_dim", advance=True)

        self._advance(SPACE_MD)

    # =======================================================================
    # Phase 2 — Section 6 (conditional): Prompt Visibility Analysis
    # =======================================================================

    def _draw_prompt_visibility(self) -> None:
        """
        Render prompt visibility. Shown ONLY when self.prompts is non-empty.
        """
        if not self.prompts:
            return

        self._check_page_break(100)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH,
            "Prompt Visibility Analysis"
        )
        self._advance(h + SPACE_SM)

        for ppr in self.prompts:
            self._check_page_break(40)
            prompt = getattr(ppr, "prompt", "") or ""
            visibility = getattr(ppr, "visibility", "not_visible")
            competitor_url = getattr(ppr, "competitor_url", None) or ""
            position = getattr(ppr, "search_position", None)

            vis_labels = {
                "exact_match":   "Found",
                "brand_visible": "Brand visible",
                "not_visible":   "Not found",
            }
            vis_label = vis_labels.get(visibility, visibility)
            position_text = f" (position #{position})" if position else ""

            self._draw_text(
                f"{prompt[:60]}",
                _FONT_KEY_BODY, 8, TEXT_MAIN,
            )
            self._advance(12)
            self._draw_text(
                f"  Status: {vis_label}{position_text}",
                _FONT_KEY_MONO, 7, TEXT_DIM,
            )
            self._advance(11)

            if competitor_url and visibility == "not_visible":
                self._draw_text(
                    f"  Ranking instead: {competitor_url[:60]}",
                    _FONT_KEY_MONO, 7, BORDER,
                )
                self._advance(11)

        self._advance(SPACE_MD)

    # =======================================================================
    # Section 7 — Competitor Comparison
    # =======================================================================

    def _draw_competitor_comparison(self) -> None:
        self._check_page_break(160)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, "Competitor Comparison"
        )
        self._advance(h + SPACE_SM)

        if not self.competitor:
            self._draw_paragraph(
                "Competitor analysis data is not available for this audit.",
                "body_dim", advance=True
            )
            self._advance(SPACE_MD)
            return

        self._check_page_break(180)
        table_h = draw_competitor_table(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, self.competitor,
        )
        self._advance(table_h + SPACE_MD)

    # =======================================================================
    # Section 8 — Metric Breakdown
    # =======================================================================

    def _draw_metric_breakdown(self) -> None:
        if not self.metrics:
            return

        self._check_page_break(60)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, "Metric Breakdown"
        )
        self._advance(h + SPACE_SM)

        intro = (
            "The 8 metrics below are the core signals that AI citation systems "
            "evaluate when deciding whether to reference a page. Each score is "
            "weighted by impact and combined into the final CQS."
        )
        self._draw_paragraph(intro, "body_dim", advance=True)
        self._advance(SPACE_SM)

        for metric in self.metrics:
            self._check_page_break(160)
            card_h = draw_metric_card(
                self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, metric,
            )
            self._advance(card_h + SPACE_SM)

    # =======================================================================
    # Section 9 — Priority Fix Plan
    # =======================================================================

    def _draw_priority_fix_plan(self) -> None:
        recommendations = []
        if self.enrichment:
            recommendations = getattr(self.enrichment, "recommendations", []) or []

        if not recommendations and self.metrics:
            for m in sorted(self.metrics, key=lambda x: x.score):
                if m.score < 50 and m.what_to_fix:
                    tier = "High Priority" if m.score < 30 else "Medium Priority"
                    recommendations.append({"priority": tier, "action": m.what_to_fix})

        self._check_page_break(80)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, "Priority Fix Plan"
        )
        self._advance(h + SPACE_SM)

        if not recommendations:
            self._draw_paragraph(
                "No specific recommendations were generated. "
                "Your page scores well across all metrics.",
                "body_dim", advance=True,
            )
            self._advance(SPACE_MD)
            return

        # Map both emoji and text tier keys
        tiers_order = ["High Priority", "Medium Priority", "Long-Term Optimization",
                       "🔥", "⚙️", "🚀"]
        tier_labels = {
            "🔥": "High Priority", "High Priority": "High Priority",
            "⚙️": "Medium Priority", "Medium Priority": "Medium Priority",
            "🚀": "Long-Term Optimization", "Long-Term Optimization": "Long-Term Optimization",
        }

        grouped: dict = {
            "High Priority": [],
            "Medium Priority": [],
            "Long-Term Optimization": [],
        }

        for rec in recommendations:
            if isinstance(rec, dict):
                p = rec.get("priority", "Medium Priority") or "Medium Priority"
                a = rec.get("action", "") or ""
            else:
                p, a = "Medium Priority", str(rec)

            # Normalise tier key
            tier_key = tier_labels.get(p, "Medium Priority")
            if a:
                grouped[tier_key].append(a)

        tier_colors = {
            "High Priority":         self._accent,
            "Medium Priority":       TEXT_DIM,
            "Long-Term Optimization": BORDER,
        }

        for tier_name in ["High Priority", "Medium Priority", "Long-Term Optimization"]:
            items = grouped[tier_name]
            if not items:
                continue

            color = tier_colors[tier_name]
            self._check_page_break(60 + len(items) * 18)
            self._draw_text(tier_name.upper(), _FONT_KEY_MONO, 8, color)
            self._advance(16)

            for action in items:
                self._check_page_break(28)
                self.canvas.saveState()
                self.canvas.setFillColor(color)
                self.canvas.circle(MARGIN_L + 5, self.current_y + 4, 3, fill=1, stroke=0)
                self.canvas.restoreState()
                self._draw_paragraph(
                    action, "body",
                    x=MARGIN_L + 14,
                    width=CONTENT_WIDTH - 14,
                    advance=True,
                )

            self._advance(SPACE_SM)

        self._advance(SPACE_MD)

    # =======================================================================
    # Section 10 — Appendix
    # =======================================================================

    def _draw_appendix(self) -> None:
        self._check_page_break(120)
        h = draw_section_divider(
            self.canvas, MARGIN_L, self.current_y, CONTENT_WIDTH, "Appendix — Methodology"
        )
        self._advance(h + SPACE_SM)

        sections = [
            (
                "About This Report",
                (
                    f"This report was generated by {self.branding.firm_name} AI Citation Analyzer. "
                    "It evaluates your webpage against the signals that large language "
                    "models and AI search systems (ChatGPT, Perplexity, Google AI "
                    "Overviews) use when deciding whether to cite a source. "
                    "No AI model was used to generate scores — all metrics are "
                    "deterministic heuristics applied consistently to every page."
                ),
            ),
            (
                "Citation Quality Score (CQS)",
                (
                    "The CQS is a weighted composite of 8 GEO (Generative Engine "
                    "Optimization) metrics. Each metric is scored 0-100 and multiplied "
                    "by its weight. The weights sum to 1.0, producing a final score "
                    "between 0 and 100. A score of 70 or above indicates a strong AI "
                    "citation candidate. 45-69 is Fair. Below 45 is Weak."
                ),
            ),
            (
                "Metric Definitions",
                (
                    "BLUF Score (15%): Measures whether the core answer appears early "
                    "in the page, reducing the work an AI must do to extract it. "
                    "Entity Density (12%): Counts proper nouns, named organisations, "
                    "dates, and specific data points as credibility signals. "
                    "Link Authority (15%): Evaluates outbound links to .gov, .edu, "
                    "and major publication domains. "
                    "Formatting Readiness (12%): Assesses H2/H3 usage, lists, and "
                    "structured content that AI systems can parse cleanly. "
                    "Schema Presence (10%): Checks for JSON-LD, FAQ schema, Article "
                    "schema, and Open Graph metadata. "
                    "Claim Support (12%): Detects inline citations, attribution "
                    "phrases, and outbound links near factual claims. "
                    "Readability (10%): Approximates Flesch reading ease using "
                    "average sentence and word length. "
                    "Search Presence (14%): Validates whether the URL or brand "
                    "appears in live search results via DuckDuckGo."
                ),
            ),
            (
                "Confidence Level",
                (
                    "The Confidence Level reflects the quality of data collected "
                    "during the audit, not the page quality itself. High confidence "
                    "means the page was fully accessible, search data was available, "
                    "and the keyword matched the content. Low confidence may indicate "
                    "a JavaScript-gated page, low search visibility, or missing inputs."
                ),
            ),
            (
                "AI Citation Variance Disclaimer",
                (
                    "When AI citation detection is included in this report, results "
                    "reflect a single session at the time of audit. AI citation "
                    "behaviour varies by session, query phrasing, and model version. "
                    "A citation found during the audit does not guarantee future "
                    "citations, and absence does not indicate permanent exclusion."
                ),
            ),
            (
                "Disclaimer",
                (
                    "Scores are calculated heuristically and represent an approximation "
                    "of AI citation likelihood based on publicly observable signals. "
                    f"{self.branding.firm_name} does not guarantee citation by any AI system. "
                    "Results should be treated as directional guidance, not absolute "
                    "metrics. Page scores may change as content, search visibility, "
                    "and AI model behaviours evolve."
                ),
            ),
        ]

        for title, body in sections:
            self._check_page_break(80)
            self._draw_text(title, _FONT_KEY_HEADING, 10, self._accent)
            self._advance(16)
            self._draw_paragraph(body, "body_dim", advance=True)
            self._advance(SPACE_SM)
            self._rule()
            self._advance(SPACE_SM)

        self._check_page_break(40)
        self._advance(SPACE_MD)
        self._draw_text(
            f"{self.branding.firm_name} — AI Citation Analyzer",
            _FONT_KEY_MONO, 7, TEXT_DIM,
            x=PAGE_WIDTH / 2,
            align="center",
        )
        self._advance(10)
        self._draw_text(
            f"Report generated {datetime.now().strftime('%B %d, %Y')}",
            _FONT_KEY_MONO, 7, TEXT_DIM,
            x=PAGE_WIDTH / 2,
            align="center",
        )