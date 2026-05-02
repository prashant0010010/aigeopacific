"""
core/confidence.py
==================
Confidence scoring layer for the AiGeoPacific AI Citation Analyser.

Responsibilities:
- Calculate a Confidence Score (0–100) reflecting how reliable the audit is
- Combine three weighted factors: data depth, search signal, keyword relevance
- Return a ConfidenceResult Pydantic model with score, level, and plain-English note

A high CQS (Citation Quality Score) can be misleading if the page could not
be fully fetched, search signals are absent, or the keyword does not appear
in the content. This module acts as the sanity-check layer that surfaces
those data quality limitations to the client.

Allowed imports: re, typing, core.models only.
No external APIs, no network calls, no heavy computation.
"""

import re
from typing import List, Optional

from core.models import (
    ConfidenceResult,
    MetricScore,
    PageConfig,
    SearchPresence,
)

# ---------------------------------------------------------------------------
# Confidence level thresholds
# ---------------------------------------------------------------------------

_LEVEL_HIGH_THRESHOLD: float = 90.0
_LEVEL_MEDIUM_THRESHOLD: float = 70.0

# ---------------------------------------------------------------------------
# Factor weights — must sum to 1.0
# ---------------------------------------------------------------------------

_WEIGHT_DATA_DEPTH: float = 0.40
_WEIGHT_SEARCH_SIGNAL: float = 0.30
_WEIGHT_KEYWORD_RELEVANCE: float = 0.30

# ---------------------------------------------------------------------------
# Keyword relevance: only inspect the first N words of page text
# ---------------------------------------------------------------------------

_KEYWORD_WINDOW_WORDS: int = 500


# ===========================================================================
# Factor calculators
# ===========================================================================


def calculate_data_depth(page_data: dict) -> float:
    """
    Score how much page content was successfully retrieved.

    Maps fetch status directly to a points value:
    - "success"        → 100 (full HTML and text available)
    - "limited_access" → 40  (partial content, likely JS-gated)
    - "failed"         → 0   (nothing retrieved)

    Parameters
    ----------
    page_data : dict
        Dictionary returned by fetcher.fetch_page().

    Returns
    -------
    float
        Raw factor score 0–100.
    """
    status = page_data.get("status", "failed")

    if status == "success":
        return 100.0
    elif status == "limited_access":
        return 40.0
    else:
        return 0.0


def calculate_search_signal(search_presence: SearchPresence) -> float:
    """
    Score the strength of search visibility for the audited page.

    Maps SearchPresence.status to a points value:
    - "exact_match"   → 100 (page URL found in results)
    - "brand_visible" → 70  (brand or title found but not exact URL)
    - "not_visible"   → 20  (no presence detected)

    Parameters
    ----------
    search_presence : SearchPresence
        Populated SearchPresence model from search_service.

    Returns
    -------
    float
        Raw factor score 0–100.
    """
    status = search_presence.status

    if status == "exact_match":
        return 100.0
    elif status == "brand_visible":
        return 70.0
    else:
        return 20.0


def calculate_keyword_relevance(
    page_data: dict,
    page_config: PageConfig,
) -> float:
    """
    Check whether the target keyword appears in the page title or
    the first 500 words of page text.

    Matching rules (case-insensitive):
    - Keyword in title         → 100 points
    - Keyword in first 500 words → 80 points
    - Keyword absent           → 20 points

    If no keyword is provided in PageConfig, returns a neutral 50 points
    (cannot penalise what was not specified).

    Parameters
    ----------
    page_data : dict
        Dictionary returned by fetcher.fetch_page().
    page_config : PageConfig
        Input configuration; PageConfig.target_keyword may be None.

    Returns
    -------
    float
        Raw factor score 0–100.
    """
    keyword = page_config.target_keyword
    if not keyword or not keyword.strip():
        # No keyword to check — return neutral score
        return 50.0

    keyword_pattern = re.compile(re.escape(keyword.strip()), re.IGNORECASE)

    # Check page title first
    title = page_data.get("title") or ""
    if title and keyword_pattern.search(title):
        return 100.0

    # Check first 500 words of page text
    text = page_data.get("text") or ""
    if text:
        words = text.split()
        window = " ".join(words[:_KEYWORD_WINDOW_WORDS])
        if keyword_pattern.search(window):
            return 80.0

    return 20.0


# ===========================================================================
# Level and note generators
# ===========================================================================


def _determine_level(score: float) -> str:
    """
    Map a confidence score to a human-readable level label.

    Parameters
    ----------
    score : float
        Confidence score 0–100.

    Returns
    -------
    str
        "High", "Medium", or "Low".
    """
    if score >= _LEVEL_HIGH_THRESHOLD:
        return "High"
    elif score >= _LEVEL_MEDIUM_THRESHOLD:
        return "Medium"
    else:
        return "Low"


def generate_confidence_note(
    level: str,
    page_status: str,
    search_status: str,
) -> str:
    """
    Generate a short, plain-English explanation of the confidence level.

    The note adapts to the specific combination of fetch status and
    search signal so the client understands exactly why confidence is
    High, Medium, or Low.

    Parameters
    ----------
    level : str
        "High", "Medium", or "Low".
    page_status : str
        Fetch status from page_data: "success", "limited_access", or "failed".
    search_status : str
        SearchPresence.status: "exact_match", "brand_visible", or "not_visible".

    Returns
    -------
    str
        A one-to-two sentence confidence note.
    """
    # Limited access always surfaces in the note regardless of level
    if page_status == "limited_access":
        return (
            "Analysis limited due to partial page access. "
            "The page appears to require JavaScript to render fully, "
            "so some metrics may be underestimated."
        )

    if page_status == "failed":
        return (
            "Low confidence: the page could not be fetched. "
            "All metric scores are set to zero and should not be used for decisions."
        )

    if level == "High":
        return (
            "High confidence: page content and search signals align strongly. "
            "Scores reflect a complete, publicly visible page."
        )

    if level == "Medium":
        if search_status == "not_visible":
            return (
                "Moderate confidence: page content was retrieved successfully "
                "but the page has low search visibility, which limits the "
                "reliability of the Search Presence score."
            )
        return (
            "Moderate confidence: some signals are weaker but sufficient "
            "data was available to produce a reliable audit."
        )

    # Low
    if search_status == "not_visible":
        return (
            "Low confidence: analysis is limited by both weak search presence "
            "and incomplete content signals. Treat scores as directional only."
        )

    return (
        "Low confidence: analysis is limited due to incomplete page data "
        "or weak search signals. Scores should be treated as indicative only."
    )


# ===========================================================================
# Main public function
# ===========================================================================


def calculate_confidence(
    page_data: dict,
    search_presence: SearchPresence,
    metric_scores: List[MetricScore],
    page_config: PageConfig,
) -> ConfidenceResult:
    """
    Calculate the audit confidence level from three weighted factors.

    Combines data depth (40%), search signal (30%), and keyword relevance
    (30%) into a single Confidence Score (0–100), then maps it to a
    level label and generates a plain-English note.

    Parameters
    ----------
    page_data : dict
        Dictionary returned by fetcher.fetch_page().
    search_presence : SearchPresence
        Populated SearchPresence model from search_service.
    metric_scores : List[MetricScore]
        The user's scored MetricScore objects (accepted for interface
        consistency and future extension; not used in Phase 1 scoring).
    page_config : PageConfig
        Input configuration containing the optional target keyword.

    Returns
    -------
    ConfidenceResult
        Populated with score (0–100), level ("High"/"Medium"/"Low"),
        and a plain-English reasoning note.
    """
    page_status = page_data.get("status", "failed")
    search_status = search_presence.status

    # --- Compute the three raw factor scores ---
    data_depth = calculate_data_depth(page_data)
    search_signal = calculate_search_signal(search_presence)
    keyword_relevance = calculate_keyword_relevance(page_data, page_config)

    # --- Weighted combination ---
    raw_score = (
        (data_depth * _WEIGHT_DATA_DEPTH)
        + (search_signal * _WEIGHT_SEARCH_SIGNAL)
        + (keyword_relevance * _WEIGHT_KEYWORD_RELEVANCE)
    )

    confidence_score = round(max(0.0, min(100.0, raw_score)), 2)

    # --- Level and note ---
    level = _determine_level(confidence_score)
    reasoning = generate_confidence_note(level, page_status, search_status)

    return ConfidenceResult(
        level=level,
        reasoning=reasoning,
    )