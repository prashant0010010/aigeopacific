"""
ui/styles.py
============
Global CSS styling layer for the AiGeoPacific AI Citation Analyser Streamlit UI.

Phase 2 additions:
- Light and dark mode CSS custom properties via data-theme attribute
- inject_theme_attribute() helper for toggling theme from app.py
- All colour references use CSS variables — no hardcoded hex in component HTML
- Default remains dark (Phase 1 behaviour preserved)

Usage:
    from ui.styles import inject_custom_css, inject_theme_attribute
    inject_custom_css()
    inject_theme_attribute(st.session_state.get("theme", "dark"))
"""

import streamlit as st

# ===========================================================================
# CSS Design System
# ===========================================================================

_CSS = """
<style>

/* =========================================================================
   Google Fonts
   ========================================================================= */

@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700&family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap');

/* =========================================================================
   Phase 2 — Theme tokens: dark (default)
   ========================================================================= */

:root,
:root[data-theme="dark"] {
    --bg-primary:        #0a0c10;
    --bg-card:           #141720;
    --bg-secondary:      #1c2030;
    --text-primary:      #f3f4f6;
    --text-secondary:    #9ca3af;
    --accent:            #f5b800;
    --accent-hover:      #ffc91a;
    --border:            #374151;
    --score-green-bg:    #166534;
    --score-green-text:  #dcfce7;
    --score-amber-bg:    #92400e;
    --score-amber-text:  #fef3c7;
    --score-red-bg:      #991b1b;
    --score-red-text:    #fee2e2;
    --shadow-card:       0 2px 12px rgba(0, 0, 0, 0.4);
    --shadow-glow:       0 4px 24px rgba(245, 184, 0, 0.12);
    --transition:        0.2s ease;

    /* Legacy aliases (Phase 1 compat) */
    --bg-dark:       #0a0c10;
    --card-bg:       #141720;
    --gold:          #f5b800;
    --gold-hover:    #ffc91a;
    --text-main:     #ffffff;
    --text-dim:      #9ca3af;
    --success:       #166534;
    --warning:       #92400e;
    --error:         #991b1b;
    --success-text:  #dcfce7;
    --warning-text:  #fef3c7;
    --error-text:    #fee2e2;

    --font-heading:  'Syne', sans-serif;
    --font-body:     'DM Sans', sans-serif;
    --font-mono:     'DM Mono', monospace;
    --radius-sm:     6px;
    --radius-md:     10px;
    --radius-lg:     14px;
}

/* =========================================================================
   Phase 2 — Theme tokens: light
   ========================================================================= */

:root[data-theme="light"] {
    --bg-primary:        #f9fafb;
    --bg-card:           #ffffff;
    --bg-secondary:      #f3f4f6;
    --text-primary:      #111827;
    --text-secondary:    #6b7280;
    --accent:            #d4a000;
    --accent-hover:      #b88c00;
    --border:            #e5e7eb;
    --score-green-bg:    #dcfce7;
    --score-green-text:  #166534;
    --score-amber-bg:    #fef3c7;
    --score-amber-text:  #92400e;
    --score-red-bg:      #fee2e2;
    --score-red-text:    #991b1b;
    --shadow-card:       0 2px 8px rgba(0, 0, 0, 0.08);
    --shadow-glow:       0 4px 16px rgba(212, 160, 0, 0.12);
    --transition:        0.2s ease;

    /* Legacy aliases */
    --bg-dark:       #f9fafb;
    --card-bg:       #ffffff;
    --gold:          #d4a000;
    --gold-hover:    #b88c00;
    --text-main:     #111827;
    --text-dim:      #6b7280;
    --success:       #dcfce7;
    --warning:       #fef3c7;
    --error:         #fee2e2;
    --success-text:  #166534;
    --warning-text:  #92400e;
    --error-text:    #991b1b;
}

/* =========================================================================
   Global Reset & Base
   ========================================================================= */

*, *::before, *::after {
    box-sizing: border-box;
}

html, body {
    background-color: var(--bg-primary) !important;
    color:            var(--text-primary) !important;
    font-family:      var(--font-body) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* =========================================================================
   Streamlit App Shell
   ========================================================================= */

.stApp {
    background-color: var(--bg-primary) !important;
    font-family:      var(--font-body) !important;
}

.block-container {
    background-color: var(--bg-primary) !important;
    padding-top:      2rem !important;
    padding-bottom:   4rem !important;
    max-width:        960px;
}

/* =========================================================================
   Sidebar
   ========================================================================= */

[data-testid="stSidebar"] {
    background-color: var(--bg-primary) !important;
    border-right:     1px solid var(--border) !important;
}

[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem !important;
}

[data-testid="stSidebarContent"] {
    background-color: var(--bg-primary) !important;
}

[data-testid="stSidebar"] a,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] p {
    color:       var(--text-secondary) !important;
    font-family: var(--font-body) !important;
    font-size:   0.875rem;
}

[data-testid="stSidebar"] a:hover {
    color: var(--accent) !important;
}

/* =========================================================================
   Typography
   ========================================================================= */

h1, h2, h3, h4, h5, h6 {
    font-family:    var(--font-heading) !important;
    color:          var(--text-primary) !important;
    letter-spacing: -0.01em;
    line-height:    1.25;
}

h1 { font-size: 2rem;   font-weight: 700; }
h2 { font-size: 1.5rem; font-weight: 700; }
h3 { font-size: 1.2rem; font-weight: 600; }
h4 { font-size: 1rem;   font-weight: 600; }

p, span, li, label, div {
    font-family: var(--font-body) !important;
    color:       var(--text-primary);
    line-height: 1.6;
}

code, pre, .mono {
    font-family:   var(--font-mono) !important;
    background:    var(--bg-card);
    color:         var(--accent);
    padding:       2px 6px;
    border-radius: var(--radius-sm);
    font-size:     0.8rem;
}

pre code {
    display:    block;
    padding:    1rem;
    overflow-x: auto;
    border:     1px solid var(--border);
}

.stMarkdown p,
.stMarkdown li,
.stMarkdown span {
    color:       var(--text-primary) !important;
    font-family: var(--font-body) !important;
}

/* =========================================================================
   Metric Cards
   ========================================================================= */

.metric-card {
    background:    var(--bg-card);
    border:        1px solid var(--border);
    border-radius: var(--radius-lg);
    padding:       1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow:    var(--shadow-card);
    transition:    transform var(--transition), box-shadow var(--transition);
    position:      relative;
    overflow:      hidden;
}

.metric-card::before {
    content:      '';
    position:     absolute;
    top:          0;
    left:         0;
    width:        3px;
    height:       100%;
    background:   var(--accent);
    border-radius: var(--radius-lg) 0 0 var(--radius-lg);
    opacity:      0;
    transition:   opacity var(--transition);
}

.metric-card:hover {
    transform:    translateY(-2px);
    box-shadow:   var(--shadow-glow);
    border-color: rgba(245, 184, 0, 0.3);
}

.metric-card:hover::before {
    opacity: 1;
}

.metric-card-title {
    font-family:    var(--font-heading);
    font-size:      0.9rem;
    font-weight:    700;
    color:          var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom:  0.5rem;
}

.metric-card-score {
    font-family:   var(--font-heading);
    font-size:     2rem;
    font-weight:   700;
    line-height:   1;
    margin-bottom: 0.5rem;
}

.metric-card-body {
    font-family: var(--font-body);
    font-size:   0.85rem;
    color:       var(--text-secondary);
    line-height: 1.55;
}

.metric-card-label {
    font-family:    var(--font-mono);
    font-size:      0.72rem;
    color:          var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* =========================================================================
   Score Badge Classes
   ========================================================================= */

.badge-strong,
.badge-fair,
.badge-weak {
    display:        inline-block;
    padding:        3px 12px;
    border-radius:  999px;
    font-family:    var(--font-mono);
    font-size:      0.75rem;
    font-weight:    600;
    letter-spacing: 0.04em;
    white-space:    nowrap;
    user-select:    none;
}

.badge-strong {
    background: var(--score-green-bg);
    color:      var(--score-green-text);
}

.badge-fair {
    background: var(--score-amber-bg);
    color:      var(--score-amber-text);
}

.badge-weak {
    background: var(--score-red-bg);
    color:      var(--score-red-text);
}

/* =========================================================================
   Progress Bars
   ========================================================================= */

.stProgress > div > div > div > div {
    background:    var(--accent) !important;
    border-radius: 999px;
}

.stProgress > div > div > div {
    background:    var(--border) !important;
    border-radius: 999px;
}

/* =========================================================================
   Buttons — Primary
   ========================================================================= */

.stButton > button {
    background:     var(--accent) !important;
    color:          #0a0c10 !important;
    border:         none !important;
    border-radius:  8px !important;
    font-family:    var(--font-body) !important;
    font-weight:    600 !important;
    font-size:      0.9rem !important;
    padding:        0.6rem 1.4rem !important;
    cursor:         pointer;
    transition:     background var(--transition), transform var(--transition), box-shadow var(--transition);
    letter-spacing: 0.01em;
    box-shadow:     0 2px 8px rgba(245, 184, 0, 0.25);
}

.stButton > button:hover {
    background:  var(--accent-hover) !important;
    transform:   translateY(-1px);
    box-shadow:  0 4px 16px rgba(245, 184, 0, 0.35) !important;
}

.stButton > button:active {
    transform:  translateY(0);
    box-shadow: 0 1px 4px rgba(245, 184, 0, 0.2) !important;
}

.stButton > button:disabled {
    background:  var(--border) !important;
    color:       var(--text-secondary) !important;
    cursor:      not-allowed;
    box-shadow:  none !important;
    transform:   none !important;
}

/* =========================================================================
   Download Button
   ========================================================================= */

[data-testid="stDownloadButton"] button {
    background:     var(--accent) !important;
    color:          #0a0c10 !important;
    border:         none !important;
    border-radius:  8px !important;
    font-family:    var(--font-body) !important;
    font-weight:    700 !important;
    font-size:      0.9rem !important;
    padding:        0.65rem 1.5rem !important;
    letter-spacing: 0.01em;
    cursor:         pointer;
    transition:     background var(--transition), transform var(--transition), box-shadow var(--transition);
    box-shadow:     0 2px 12px rgba(245, 184, 0, 0.3);
}

[data-testid="stDownloadButton"] button:hover {
    background:  var(--accent-hover) !important;
    transform:   translateY(-1px);
    box-shadow:  0 6px 20px rgba(245, 184, 0, 0.4) !important;
}

/* =========================================================================
   Input Fields
   ========================================================================= */

.stTextInput > div > div > input,
.stTextArea textarea {
    background:    var(--bg-card) !important;
    border:        1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    color:         var(--text-primary) !important;
    font-family:   var(--font-body) !important;
    font-size:     0.9rem !important;
    transition:    border-color var(--transition), box-shadow var(--transition);
}

.stTextInput > div > div > input:focus,
.stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow:   0 0 0 3px rgba(245, 184, 0, 0.15) !important;
    outline:      none !important;
}

.stTextInput > div > div > input::placeholder,
.stTextArea textarea::placeholder {
    color: var(--text-secondary) !important;
}

.stTextInput label,
.stTextArea label,
.stSelectbox label,
.stCheckbox label {
    color:          var(--text-secondary) !important;
    font-family:    var(--font-mono) !important;
    font-size:      0.75rem !important;
    font-weight:    500 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* =========================================================================
   Tabs
   ========================================================================= */

.stTabs [data-baseweb="tab-list"] {
    background:    transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap:           0.25rem;
}

.stTabs [data-baseweb="tab"] {
    background:    transparent !important;
    color:         var(--text-secondary) !important;
    font-family:   var(--font-body) !important;
    font-size:     0.875rem !important;
    font-weight:   500 !important;
    border:        none !important;
    border-bottom: 2px solid transparent !important;
    padding:       0.5rem 1rem !important;
    transition:    color var(--transition), border-color var(--transition);
}

.stTabs [aria-selected="true"] {
    color:         var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background:    transparent !important;
}

/* =========================================================================
   Expander
   ========================================================================= */

.streamlit-expanderHeader {
    background:    var(--bg-card) !important;
    border:        1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    color:         var(--text-primary) !important;
    font-family:   var(--font-body) !important;
    font-weight:   500 !important;
}

.streamlit-expanderContent {
    background:    var(--bg-card) !important;
    border:        1px solid var(--border) !important;
    border-top:    none !important;
    border-radius: 0 0 var(--radius-md) var(--radius-md) !important;
}

/* =========================================================================
   Metrics (st.metric)
   ========================================================================= */

[data-testid="stMetricValue"] {
    font-family: var(--font-heading) !important;
    color:       var(--accent) !important;
    font-size:   2rem !important;
    font-weight: 700 !important;
}

[data-testid="stMetricLabel"] {
    font-family:    var(--font-mono) !important;
    color:          var(--text-secondary) !important;
    font-size:      0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* =========================================================================
   Dividers
   ========================================================================= */

hr {
    border-color: var(--border) !important;
    margin:       1.5rem 0 !important;
}

/* =========================================================================
   Spinner
   ========================================================================= */

.stSpinner > div {
    border-top-color: var(--accent) !important;
}

/* =========================================================================
   Scrollbar
   ========================================================================= */

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }

/* =========================================================================
   Utility Classes
   ========================================================================= */

.section-block {
    background:    var(--bg-card);
    border:        1px solid var(--border);
    border-radius: var(--radius-lg);
    padding:       1.5rem;
    margin-bottom: 1.5rem;
}

.gold-label {
    font-family:    var(--font-mono);
    font-size:      0.72rem;
    font-weight:    500;
    color:          var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom:  0.4rem;
}

.dim-text {
    color:       var(--text-secondary);
    font-size:   0.85rem;
    line-height: 1.55;
}

.tag-pill {
    display:       inline-block;
    background:    rgba(245, 184, 0, 0.1);
    border:        1px solid rgba(245, 184, 0, 0.25);
    color:         var(--accent);
    font-family:   var(--font-mono);
    font-size:     0.7rem;
    padding:       2px 8px;
    border-radius: 999px;
    margin-right:  4px;
    white-space:   nowrap;
}

.gap-item {
    display:       flex;
    align-items:   flex-start;
    gap:           0.5rem;
    margin-bottom: 0.5rem;
    font-size:     0.875rem;
    color:         var(--text-primary);
    line-height:   1.5;
}

.gap-item::before {
    content:    "->";
    color:      var(--accent);
    flex-shrink: 0;
    margin-top:  1px;
    font-family: var(--font-mono);
    font-size:   0.75rem;
}

.score-number {
    font-family: var(--font-heading);
    font-size:   3rem;
    font-weight: 700;
    line-height: 1;
    color:       var(--accent);
}

/* =========================================================================
   Phase 2 — Citation detected card
   ========================================================================= */

.citation-card {
    background:    rgba(22, 101, 52, 0.12);
    border:        1px solid rgba(34, 197, 94, 0.3);
    border-radius: var(--radius-md);
    padding:       0.75rem 1rem;
    margin-bottom: 0.6rem;
}

.citation-card-domain {
    font-family: var(--font-mono);
    font-size:   0.72rem;
    color:       #4ade80;
    font-weight: 600;
}

.citation-card-snippet {
    font-family: var(--font-body);
    font-size:   0.82rem;
    color:       var(--text-secondary);
    margin-top:  0.25rem;
    line-height: 1.5;
}

/* =========================================================================
   Phase 2 — Delta / progress comparison
   ========================================================================= */

.delta-positive {
    color:       #4ade80;
    font-weight: 700;
    font-family: var(--font-mono);
}

.delta-negative {
    color:       #f87171;
    font-weight: 700;
    font-family: var(--font-mono);
}

.delta-neutral {
    color:       var(--text-secondary);
    font-family: var(--font-mono);
}

/* =========================================================================
   Phase 2 — Prompt visibility row
   ========================================================================= */

.prompt-row {
    display:       flex;
    align-items:   center;
    gap:           0.75rem;
    padding:       0.5rem 0.75rem;
    background:    var(--bg-card);
    border:        1px solid var(--border);
    border-radius: var(--radius-sm);
    margin-bottom: 0.4rem;
}

.prompt-row-text {
    font-family: var(--font-body);
    font-size:   0.875rem;
    color:       var(--text-primary);
    flex:        1;
}

/* =========================================================================
   Hide Streamlit Branding
   ========================================================================= */

footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
[data-testid="stToolbar"] { visibility: hidden; }

header[data-testid="stHeader"] {
    background:    transparent !important;
    border-bottom: none !important;
}

</style>
"""

# ===========================================================================
# Injection helpers
# ===========================================================================


def inject_custom_css() -> None:
    """
    Inject the AiGeoPacific custom CSS into the active Streamlit session.

    Must be called once at the top of app.py before any other Streamlit
    widgets are rendered. Calling it multiple times is harmless.
    """
    st.markdown(_CSS, unsafe_allow_html=True)


def inject_theme_attribute(theme: str = "dark") -> None:
    """
    Set the data-theme attribute on the root element to enable theme switching.

    Injects a small JS snippet that sets document.documentElement.setAttribute().
    Must be called after inject_custom_css().

    Parameters
    ----------
    theme : str
        "dark" (default) or "light"
    """
    safe_theme = "light" if theme == "light" else "dark"
    st.markdown(
        f"""
        <script>
            document.documentElement.setAttribute('data-theme', '{safe_theme}');
        </script>
        """,
        unsafe_allow_html=True,
    )