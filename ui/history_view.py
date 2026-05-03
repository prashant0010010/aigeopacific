"""
ui/history_view.py
AiGeoPacific — Audit History Sidebar Panel (Phase 2)

Fixes applied:
  - Each "Load report" button uses key=f"load_{i}" so Streamlit treats
    them as distinct widgets and the click handler loads history_list[i].
  - Each "Compare with previous" button uses key=f"compare_{i}" and
    compares history_list[i] against the immediately preceding audit for
    that same domain (history_list[i+1] in the domain-filtered slice),
    not always the two most-recent entries.
  - Callback functions receive the index explicitly via a default-argument
    capture (idx=i) to avoid the classic Python late-binding closure bug.
"""

from __future__ import annotations

import streamlit as st

from core.storage import list_audits, load_audit, delete_audit
from core.delta import compute_delta
from core.models import AuditResult


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _domain(url: str) -> str:
    """Return a normalised domain string for grouping audits."""
    import re
    url = url.lower().strip()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.split("/")[0]


def _sorted_history() -> list[dict]:
    """
    Return audit metadata sorted newest-first.
    Each entry is the dict returned by list_audits(), e.g.:
        {"audit_id": str, "url": str, "timestamp": str, "cqs": float, ...}
    """
    try:
        return list_audits()  # already sorted newest-first by storage layer
    except Exception:
        return []


def _audits_for_domain(history: list[dict], domain: str) -> list[dict]:
    """
    Return all history entries whose URL matches *domain*, preserving the
    existing newest-first order.
    """
    return [entry for entry in history if _domain(entry.get("url", "")) == domain]


# ---------------------------------------------------------------------------
# Callbacks — defined at module level so Streamlit can serialise them.
# The idx default-argument capture is the standard Python idiom to avoid
# the closure bug where all lambdas would share the final loop value of i.
# ---------------------------------------------------------------------------

def _cb_load(idx: int, history: list[dict]) -> None:
    """Load the audit at position *idx* in *history* into session state."""
    entry = history[idx]
    try:
        result: AuditResult = load_audit(entry["audit_id"])
        st.session_state["audit_result"] = result
        st.session_state["loaded_from_history"] = True
        st.session_state["loaded_audit_id"] = entry["audit_id"]
        st.toast(f"Loaded audit for {entry.get('url', 'unknown')}", icon="📂")
    except Exception as exc:
        st.error(f"Could not load audit: {exc}")


def _cb_delete(idx: int, history: list[dict]) -> None:
    """Delete the audit at position *idx* from storage."""
    entry = history[idx]
    try:
        delete_audit(entry["audit_id"])
        # Clear cached list so the sidebar re-fetches on next render.
        if "history_cache" in st.session_state:
            del st.session_state["history_cache"]
        st.toast("Audit deleted.", icon="🗑️")
    except Exception as exc:
        st.error(f"Could not delete audit: {exc}")


def _cb_compare(idx: int, history: list[dict]) -> None:
    """
    Compare the audit at *idx* with the immediately preceding audit for the
    same domain.

    *history* is the full (newest-first) list.  We find all audits for the
    same domain, then compare history[idx] (the "newer" one) against the
    next entry in that domain-filtered list (the "older" one).
    """
    entry = history[idx]
    domain = _domain(entry.get("url", ""))
    domain_audits = _audits_for_domain(history, domain)

    # Find where *entry* sits inside the domain-filtered list.
    try:
        pos_in_domain = next(
            j for j, e in enumerate(domain_audits) if e["audit_id"] == entry["audit_id"]
        )
    except StopIteration:
        st.error("Could not locate this audit in the domain history.")
        return

    if pos_in_domain + 1 >= len(domain_audits):
        st.warning("No earlier audit for this domain to compare against.")
        return

    newer_meta = domain_audits[pos_in_domain]      # the one the user clicked
    older_meta = domain_audits[pos_in_domain + 1]  # immediately before it

    try:
        newer: AuditResult = load_audit(newer_meta["audit_id"])
        older: AuditResult = load_audit(older_meta["audit_id"])
    except Exception as exc:
        st.error(f"Could not load audits for comparison: {exc}")
        return

    try:
        delta = compute_delta(older, newer)
        st.session_state["compare_delta"] = delta
        st.session_state["compare_newer"] = newer
        st.session_state["compare_older"] = older
        st.toast("Comparison ready — scroll to the delta banner.", icon="📊")
    except Exception as exc:
        st.error(f"Delta computation failed: {exc}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_history_panel() -> None:
    """
    Render the audit history sidebar panel.

    Call this from app.py inside a `with st.sidebar:` block or wherever the
    history panel should appear.
    """
    st.markdown("### 🗂️ Audit History")

    # Cache the history list for this render cycle so every button callback
    # sees the same snapshot.  We store it on session_state keyed by a
    # simple sentinel so a delete invalidates it (see _cb_delete).
    if "history_cache" not in st.session_state:
        st.session_state["history_cache"] = _sorted_history()

    history: list[dict] = st.session_state["history_cache"]

    if not history:
        st.caption("No saved audits yet. Run an audit to build history.")
        return

    # -----------------------------------------------------------------------
    # Render one expander row per saved audit.
    # i is the position in the *full* history list (newest-first).
    # Using i in every key and callback ensures uniqueness and correct index.
    # -----------------------------------------------------------------------
    for i, entry in enumerate(history):
        url = entry.get("url", "Unknown URL")
        timestamp = entry.get("timestamp", "")
        cqs = entry.get("cqs", None)

        # Build a short display label.
        short_url = url.replace("https://", "").replace("http://", "").rstrip("/")
        if len(short_url) > 40:
            short_url = short_url[:37] + "…"

        cqs_label = f"CQS {cqs:.0f}" if cqs is not None else "CQS —"
        expander_label = f"{short_url}  ·  {cqs_label}  ·  {timestamp[:10]}"

        with st.expander(expander_label, expanded=False):
            st.caption(f"Full URL: {url}")
            if timestamp:
                st.caption(f"Audited: {timestamp}")

            col_load, col_compare, col_delete = st.columns([2, 2, 1])

            # ------------------------------------------------------------------
            # LOAD button
            # Key must be unique across all rows → include i.
            # on_click captures i via default arg to avoid late-binding bug.
            # ------------------------------------------------------------------
            with col_load:
                st.button(
                    "📂 Load report",
                    key=f"load_{i}",
                    on_click=_cb_load,
                    args=(i, history),
                    use_container_width=True,
                )

            # ------------------------------------------------------------------
            # COMPARE button
            # Only shown when there is at least one earlier audit for this domain.
            # ------------------------------------------------------------------
            domain = _domain(url)
            domain_audits = _audits_for_domain(history, domain)
            try:
                pos_in_domain = next(
                    j for j, e in enumerate(domain_audits)
                    if e["audit_id"] == entry["audit_id"]
                )
            except StopIteration:
                pos_in_domain = 0

            has_previous = pos_in_domain + 1 < len(domain_audits)

            with col_compare:
                if has_previous:
                    prev_date = domain_audits[pos_in_domain + 1].get("timestamp", "")[:10]
                    st.button(
                        f"📊 vs {prev_date}",
                        key=f"compare_{i}",
                        on_click=_cb_compare,
                        args=(i, history),
                        use_container_width=True,
                        help=f"Compare this audit against the one from {prev_date}",
                    )
                else:
                    # Render a disabled placeholder so the layout stays stable.
                    st.button(
                        "📊 Compare",
                        key=f"compare_{i}",
                        disabled=True,
                        use_container_width=True,
                        help="No earlier audit for this domain",
                    )

            # ------------------------------------------------------------------
            # DELETE button
            # ------------------------------------------------------------------
            with col_delete:
                st.button(
                    "🗑️",
                    key=f"delete_{i}",
                    on_click=_cb_delete,
                    args=(i, history),
                    use_container_width=True,
                    help="Delete this audit from history",
                )

    # -----------------------------------------------------------------------
    # Refresh button — clears the cache so the list re-fetches from storage.
    # -----------------------------------------------------------------------
    st.divider()
    if st.button("🔄 Refresh history", key="refresh_history"):
        if "history_cache" in st.session_state:
            del st.session_state["history_cache"]
        st.rerun()