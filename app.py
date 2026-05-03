"""
app.py
======
Main entry point for the AiGeoPacific AI Citation Analyser Streamlit application.

Phase 2 additions:
- PDF wiring: PDFBuilder.build_bytes() called after audit, wired to download button
- Light/dark mode toggle in sidebar
- Keyword prompt inputs (up to 5) passed into PageConfig.keyword_prompts
- Perplexity API key input (optional, for citation detection)
- White-label branding panel (collapsible) — firm name, accent colour, logo upload
- History panel: history_view.history_panel() rendered in sidebar
- Audit save: storage.save_audit() called after every successful audit

Live progress (Fix 3):
- run_audit() accepts a progress_callback that fires at each pipeline step.
- The callback writes a plain-text status line into a st.empty() widget,
  appending the elapsed wall-clock time in seconds so the user always sees
  something moving rather than a frozen spinner.

Architectural rule: zero business logic in this file.
"""

import io
import os
import re
import tempfile
import time
from datetime import datetime

import streamlit as st

# ---------------------------------------------------------------------------
# Optional: load .env file
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.audit_runner import run_audit
from core.models import PageConfig
from reports.pdf_builder import BrandingConfig, PDFBuilder
from ui.history_view import history_panel
from ui.results_view import render_audit_results
from ui.styles import inject_custom_css, inject_theme_attribute

# ===========================================================================
# Page configuration — must be the first Streamlit call
# ===========================================================================

st.set_page_config(
    page_title="AiGeoPacific - AI Citation Analyzer | GEO",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

# ===========================================================================
# Session state initialisation
# ===========================================================================

_STATE_DEFAULTS = {
    "audit_status":   "idle",
    "audit_result":   None,
    "pdf_buffer":     None,
    "last_url":       "",
    "theme":          "dark",
    "history_delta":  None,
    "_error_msg":     "",
}

for key, default in _STATE_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Inject theme attribute after CSS
inject_theme_attribute(st.session_state.theme)

# ===========================================================================
# Sidebar
# ===========================================================================

with st.sidebar:
    st.markdown(
        """
        <div style="padding:0.5rem 0 1rem 0;">
            <p style="font-family:'Syne',sans-serif; font-size:1.1rem;
                      font-weight:700; color:var(--accent); margin:0;">
                AiGeoPacific
            </p>
            <p style="font-family:'DM Mono',monospace; font-size:0.7rem;
                      color:var(--text-secondary); text-transform:uppercase;
                      letter-spacing:0.08em; margin:0;">
                AI Citation Analyzer
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # --- Theme toggle (Phase 2) ---
    theme_dark = st.toggle(
        "Dark mode",
        value=(st.session_state.theme == "dark"),
        help="Switch between dark and light report themes.",
    )
    new_theme = "dark" if theme_dark else "light"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        inject_theme_attribute(new_theme)
        st.rerun()

    st.divider()

    # --- Gemini API Key ---
    env_gemini_key = os.environ.get("GEMINI_API_KEY", "")
    gemini_key = st.text_input(
        "Gemini API Key",
        value=env_gemini_key,
        type="password",
        placeholder="Optional — enables AI enrichment",
        help="Google Gemini key for AI-generated report narrative. Heuristic fallback if blank.",
    )
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

    # --- Perplexity API Key (Phase 2) ---
    env_perplexity_key = os.environ.get("PERPLEXITY_API_KEY", "")
    perplexity_key = st.text_input(
        "Perplexity API Key",
        value=env_perplexity_key,
        type="password",
        placeholder="Optional — enables AI citation detection",
        help="Perplexity sonar-small-online key for live citation checking. Falls back to DuckDuckGo AI.",
    )
    if perplexity_key:
        os.environ["PERPLEXITY_API_KEY"] = perplexity_key

    st.divider()

    # --- Optional keyword ---
    target_keyword = st.text_input(
        "Target Keyword (optional)",
        placeholder="e.g. AI SEO guide",
        help="Primary query your page should rank for. Improves BLUF and confidence scoring.",
    )

    # --- Brand name ---
    brand_name = st.text_input(
        "Brand Name (optional)",
        placeholder="e.g. Acme Corp",
        help="Used for search presence matching. Inferred from domain if blank.",
    )

    st.divider()

    # --- Keyword Prompts (Phase 2) ---
    st.markdown(
        '<p style="font-family:\'DM Mono\',monospace; font-size:0.72rem; '
        'color:var(--text-secondary); text-transform:uppercase; '
        'letter-spacing:0.06em; margin-bottom:0.25rem;">Prompt Visibility Testing</p>',
        unsafe_allow_html=True,
    )
    st.caption("Enter up to 5 queries you want your page to rank for in AI answers.")

    keyword_prompts = []
    for i in range(5):
        p = st.text_input(
            f"Prompt {i + 1}",
            key=f"prompt_{i}",
            placeholder="e.g. best tools for GEO",
            label_visibility="collapsed",
        )
        if p.strip():
            keyword_prompts.append(p.strip())

    st.divider()

    # --- Mock mode ---
    mock_mode = st.toggle(
        "Mock Mode",
        value=False,
        help="Load from a local HTML file instead of fetching live URLs.",
    )

    st.divider()

    # --- White-label branding (Phase 2) ---
    with st.expander("Branding (white-label)", expanded=False):
        firm_name_input = st.text_input(
            "Firm name",
            value="AiGeoPacific",
            placeholder="Your agency or company name",
        )
        accent_color_input = st.color_picker(
            "Accent colour",
            value="#c49b00",
        )
        logo_file = st.file_uploader(
            "Logo (PNG/JPG, max 2 MB)",
            type=["png", "jpg", "jpeg"],
            help="Displayed in the top-right of the PDF cover page.",
        )
        st.caption("Branding is applied to the PDF report only.")

    st.divider()

    # --- Audit History (Phase 2) ---
    history_panel()

    st.divider()

    # --- About ---
    st.markdown(
        """
        <p style="font-family:'DM Sans',sans-serif; font-size:0.8rem;
                  color:var(--text-secondary); line-height:1.6;">
            AiGeoPacific analyzes why AI systems are not citing your content
            and shows you exactly what to fix, ranked by impact.
        </p>
        <p style="font-family:'DM Mono',monospace; font-size:0.68rem;
                  color:var(--border); margin-top:0.5rem;">
            v2.0 — Phase 2
        </p>
        """,
        unsafe_allow_html=True,
    )

# ===========================================================================
# Main UI Router
# ===========================================================================

# ---------------------------------------------------------------------------
# Loaded from history — treat as complete without re-running
# ---------------------------------------------------------------------------

if st.session_state.get("result") and st.session_state.audit_status == "idle":
    # history_view.py sets session_state.result directly
    st.session_state.audit_result = st.session_state.result
    st.session_state.audit_status = "complete"
    st.session_state.result = None

# ---------------------------------------------------------------------------
# STATE: idle
# ---------------------------------------------------------------------------

if st.session_state.audit_status == "idle":

    st.markdown(
        """
        <div style="padding:1rem 0 0.5rem 0;">
            <h1 style="font-family:'Syne',sans-serif; font-size:2rem;
                       font-weight:700; color:var(--text-primary); margin:0; line-height:1.2;">
                AI Citation
                <span style="color:var(--accent);">Analyzer</span>
            </h1>
            <p style="font-family:'DM Sans',sans-serif; font-size:1rem;
                      color:var(--text-secondary); margin-top:0.5rem; max-width:620px;">
                Discover exactly why ChatGPT, Perplexity, and Google AI Overviews
                are not citing your pages — and get a prioritized fix plan.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-bottom:1.5rem;'></div>", unsafe_allow_html=True)

    url_input = st.text_input(
        "Page URL to Audit",
        value=st.session_state.last_url,
        placeholder="https://yourdomain.com/your-page",
        help="Enter the full URL of the page you want to analyse.",
    )

    col_btn, col_hint = st.columns([1, 4])

    with col_btn:
        run_clicked = st.button("Run Audit", type="primary", use_container_width=True)

    with col_hint:
        st.markdown(
            '<p style="font-family:\'DM Mono\',monospace; font-size:0.72rem; '
            'color:var(--text-secondary); padding-top:0.6rem;">'
            'Audit takes 15-40 seconds depending on page and competitor fetch times.'
            '</p>',
            unsafe_allow_html=True,
        )

    if run_clicked:
        url_clean = (url_input or "").strip()
        if not url_clean:
            st.warning("Please enter a valid URL before running the audit.")
        elif not url_clean.startswith(("http://", "https://")):
            st.warning("URL must start with http:// or https://")
        else:
            st.session_state.last_url = url_clean
            st.session_state.audit_status = "running"
            st.rerun()

# ---------------------------------------------------------------------------
# STATE: running
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# STATE: running
# ---------------------------------------------------------------------------

elif st.session_state.audit_status == "running":

    url = st.session_state.last_url

    st.markdown(
        f"""
        <div style="margin-bottom:1.5rem;">
            <p style="font-family:'DM Mono',monospace; font-size:0.72rem;
                      color:var(--text-secondary); text-transform:uppercase;
                      letter-spacing:0.08em; margin-bottom:0.25rem;">Analyzing</p>
            <p style="font-family:'DM Sans',sans-serif; font-size:0.95rem;
                      color:var(--accent); margin:0; word-break:break-all;">{url}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # Live status widget — updated by the progress_callback below.
    # A single st.empty() is the correct pattern: repeated .markdown()
    # calls on the same element replace the content in place without
    # accumulating new DOM nodes or triggering a full rerun.
    # ------------------------------------------------------------------
    status_placeholder = st.empty()
    audit_wall_start = time.time()

    def _make_status_html(msg: str) -> str:
        """Render a status line with elapsed seconds."""
        elapsed = int(time.time() - audit_wall_start)
        return (
            f'<p style="font-family:\'DM Mono\',monospace; font-size:0.82rem; '
            f'color:var(--text-secondary); margin:0.1rem 0;">'
            f'⏳ {msg} <span style="color:var(--border);">({elapsed}s)</span></p>'
        )

    def _progress_callback(step: str) -> None:
        """
        Called by audit_runner at the start of each pipeline step.

        Updates the status placeholder in place.  Any Streamlit exception
        (e.g. widget no longer in DOM) is caught and ignored so the audit
        pipeline is never interrupted by a UI hiccup.
        """
        try:
            status_placeholder.markdown(
                _make_status_html(step),
                unsafe_allow_html=True,
            )
        except Exception:
            pass

    # Show the first message immediately so the widget is never blank
    _progress_callback("Fetching page content...")

    try:
        # Build PageConfig (Phase 2: includes keyword_prompts, api keys)
        config = PageConfig(
            url=url,
            target_keyword=target_keyword.strip() if target_keyword else None,
            brand_name=brand_name.strip() if brand_name else None,
            keyword_prompts=keyword_prompts if keyword_prompts else [],
            gemini_api_key=gemini_key.strip() if gemini_key else None,
            perplexity_api_key=perplexity_key.strip() if perplexity_key else None,
        )

        result = run_audit(config, progress_callback=_progress_callback)

        # -----------------------------------------------------------------------
        # Phase 2 — PDF wiring: build_bytes() and store in session state
        # -----------------------------------------------------------------------
        _progress_callback("Building your report...")

        # Resolve branding config from sidebar inputs
        logo_path = None
        if logo_file is not None:
            try:
                suffix = ".png" if logo_file.type == "image/png" else ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(logo_file.read())
                    logo_path = tmp.name
            except Exception:
                logo_path = None

        branding = BrandingConfig(
            firm_name=firm_name_input.strip() if firm_name_input.strip() else "AiGeoPacific",
            primary_color=accent_color_input or "#c49b00",
            logo_path=logo_path,
            footer_text=f"Confidential — {firm_name_input.strip() or 'AiGeoPacific'}",
        )

        try:
            pdf_bytes = PDFBuilder(result, branding=branding).build_bytes()
        except Exception as pdf_exc:
            print(f"[App] PDF generation failed: {pdf_exc}")
            pdf_bytes = None

        elapsed_total = int(time.time() - audit_wall_start)
        status_placeholder.markdown(
            f'<p style="font-family:\'DM Mono\',monospace; font-size:0.82rem; '
            f'color:var(--score-green-text); margin:0.1rem 0;">'
            f'✓ Audit complete in {elapsed_total}s</p>',
            unsafe_allow_html=True,
        )

        st.session_state.audit_result = result
        st.session_state.audit_status = "complete"
        st.session_state.pdf_buffer = pdf_bytes

    except Exception as exc:
        st.session_state.audit_status = "error"
        st.session_state._error_msg = str(exc)

    st.rerun()

# ---------------------------------------------------------------------------
# STATE: complete
# ---------------------------------------------------------------------------

elif st.session_state.audit_status == "complete":

    result = st.session_state.audit_result

    col_url, col_reset = st.columns([5, 1])

    with col_url:
        audited_url = getattr(result, "url", st.session_state.last_url)
        st.markdown(
            f"""
            <div style="padding:0.25rem 0 0.75rem 0;">
                <span style="font-family:'DM Mono',monospace; font-size:0.68rem;
                             color:var(--text-secondary); text-transform:uppercase;
                             letter-spacing:0.08em;">Audited URL</span><br>
                <span style="font-family:'DM Sans',sans-serif; font-size:0.9rem;
                             color:var(--accent); word-break:break-all;">{audited_url}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_reset:
        if st.button("New Audit", use_container_width=True):
            st.session_state.audit_status = "idle"
            st.session_state.audit_result = None
            st.session_state.pdf_buffer = None
            st.rerun()

    render_audit_results(result, pdf_buffer=st.session_state.pdf_buffer)

# ---------------------------------------------------------------------------
# STATE: error
# ---------------------------------------------------------------------------

elif st.session_state.audit_status == "error":

    error_msg = st.session_state.get("_error_msg", "An unexpected error occurred.")
    st.error(f"Audit failed: {error_msg}")

    st.markdown(
        '<p style="font-family:\'DM Sans\',sans-serif; font-size:0.875rem; '
        'color:var(--text-secondary); margin-top:0.5rem;">'
        'This may be due to a network error, an inaccessible URL, or a '
        'temporary service issue. Please check the URL and try again.'
        '</p>',
        unsafe_allow_html=True,
    )

    if st.button("Reset and Try Again", type="primary"):
        for key in ["audit_status", "audit_result", "pdf_buffer", "_error_msg"]:
            st.session_state[key] = _STATE_DEFAULTS.get(key)
        st.rerun()