"""
services/search_service.py
==========================
Reality Validation Layer for the AiGeoPacific AI Citation Analyser.

Phase 2 additions:
- TTL cache integration via core.cache.TTLCache (module-level instance)
- check_prompt_presence() for multi-keyword prompt visibility testing
- Cache key format: "ddg:{query.lower().strip()}"

Responsibilities:
- Determine whether a page or brand is visible in DuckDuckGo search results
- Return a SearchPresence Pydantic model with a status, score, and match details
- Cache results for 1 hour to prevent rate-limiting during demos
- Never crash the audit pipeline — all exceptions return a safe fallback
"""

import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import List, Optional
from urllib.parse import urlparse

from duckduckgo_search import DDGS

from core.cache import TTLCache
from core.models import PromptPresenceResult, SearchPresence

# ---------------------------------------------------------------------------
# Module-level cache — isolated to this service, not a global singleton
# ---------------------------------------------------------------------------

_cache = TTLCache(ttl_seconds=3600)

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

_SCORE_EXACT_MATCH: float = 100.0
_SCORE_BRAND_IN_TITLE: float = 80.0
_SCORE_BRAND_IN_SNIPPET: float = 70.0
_SCORE_PARTIAL_TITLE_MATCH: float = 60.0
_SCORE_DOMAIN_PRESENT: float = 30.0
_SCORE_NOT_VISIBLE: float = 0.0

_MAX_RESULTS: int = 30
_MIN_TITLE_WORD_OVERLAP: int = 2

# Hard cap on a single DuckDuckGo network call.  A DDGS() call that hangs
# (rate-limit back-off, slow DNS, etc.) will be abandoned after this many
# seconds and an empty list returned instead of blocking the whole pipeline.
_DDG_CALL_TIMEOUT: int = 8


# ===========================================================================
# URL / query helpers
# ===========================================================================


def extract_domain(url: str) -> str:
    """
    Extract the bare domain name from a URL (without www or TLD detail).

    Example:
        "https://www.openai.com/blog/post" -> "openai"

    Parameters
    ----------
    url : str
    Returns
    -------
    str
        Lowercase domain label, or empty string if parsing fails.
    """
    try:
        hostname = urlparse(url).hostname or ""
        hostname = re.sub(r"^www\.", "", hostname)
        return hostname.split(".")[0].lower()
    except Exception:
        return ""


def extract_domain_full(url: str) -> str:
    """
    Extract the full hostname from a URL, stripping www only.

    Example:
        "https://www.openai.com/blog/post" -> "openai.com"

    Parameters
    ----------
    url : str
    Returns
    -------
    str
    """
    try:
        hostname = urlparse(url).hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception:
        return ""


def extract_slug(url: str) -> str:
    """
    Extract a human-readable keyword phrase from the URL path slug.

    Parameters
    ----------
    url : str
    Returns
    -------
    str
    """
    try:
        path = urlparse(url).path or ""
        segments = [s for s in path.split("/") if s]
        if not segments:
            return ""
        slug = segments[-1]
        slug = re.sub(r"\.\w{2,5}$", "", slug)
        slug = re.sub(r"[-_]+", " ", slug)
        return slug.strip().lower()
    except Exception:
        return ""


def infer_query(
    url: str,
    brand_name: Optional[str],
    page_title: Optional[str],
) -> str:
    """
    Choose the best search query for this page using a priority cascade.

    Priority: page_title > brand_name > URL slug > raw URL.

    Parameters
    ----------
    url : str
    brand_name : Optional[str]
    page_title : Optional[str]
    Returns
    -------
    str
    """
    if page_title and page_title.strip():
        return page_title.strip()
    if brand_name and brand_name.strip():
        return brand_name.strip()
    slug = extract_slug(url)
    if slug:
        return slug
    return url


def _sanitise_brand(url: str, brand_name: Optional[str]) -> str:
    """Return a usable brand string, falling back to the domain label."""
    if brand_name and brand_name.strip():
        return brand_name.strip().lower()
    return extract_domain(url)


# ===========================================================================
# Search execution (with cache)
# ===========================================================================


def run_search(query: str) -> List[dict]:
    """
    Execute a single DuckDuckGo text search and return raw results.

    Checks the module-level TTL cache before hitting the network.
    Cache key format: "ddg:{query.lower().strip()}"
    Stores successful results in cache for 1 hour.

    Adds a small random delay when a live request is made to reduce
    rate-limiting risk. Returns an empty list on any exception.

    Parameters
    ----------
    query : str
    Returns
    -------
    List[dict]
        Up to _MAX_RESULTS result dicts with "href", "title", "body".
        Returns empty list on failure.
    """
    cache_key = f"ddg:{query.lower().strip()}"

    # --- Cache hit ---
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # --- Live request ---
    # Add a small random delay to reduce rate-limiting risk.
    time.sleep(random.uniform(0.5, 1.5))

    def _do_ddg_search() -> List[dict]:
        """Inner call — runs inside a worker thread so we can time it out."""
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=_MAX_RESULTS)
            return list(results) if results else []

    try:
        # submit() + result(timeout=N) is the standard pattern for applying a
        # wall-clock cap to a blocking call without asyncio.  A single slow
        # DDG query can never block the audit pipeline for more than
        # _DDG_CALL_TIMEOUT seconds.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_ddg_search)
            try:
                result_list = future.result(timeout=_DDG_CALL_TIMEOUT)
            except FuturesTimeoutError:
                future.cancel()
                return []

        if result_list:
            _cache.set(cache_key, result_list)

        return result_list

    except Exception:
        return []


# ===========================================================================
# Result scoring
# ===========================================================================


def score_results(
    results: List[dict],
    url: str,
    brand: str,
    page_title: Optional[str],
) -> SearchPresence:
    """
    Walk search results through the 3-tier presence validation logic.

    Tier 1 — Exact URL match  (score 100, status "exact_match")
    Tier 2 — Brand / title match (score 60-80, status "brand_visible")
    Tier 3 — Domain presence  (score 30, status "not_visible")
    Tier 4 — No presence      (score 0,  status "not_visible")

    Parameters
    ----------
    results : List[dict]
    url : str
    brand : str
    page_title : Optional[str]
    Returns
    -------
    SearchPresence
    """
    if not results:
        return SearchPresence(
            status="not_visible",
            score=_SCORE_NOT_VISIBLE,
            found_url=None,
            matched_text="Search data unavailable",
        )

    normalised_url = url.rstrip("/").lower()
    domain = extract_domain(url)

    title_tokens: set = set()
    if page_title:
        title_tokens = set(re.findall(r"[a-z]{3,}", page_title.lower()))

    # Tier 1: Exact URL match
    for result in results:
        result_href = (result.get("href") or "").rstrip("/").lower()
        if result_href == normalised_url:
            return SearchPresence(
                status="exact_match",
                score=_SCORE_EXACT_MATCH,
                found_url=result.get("href"),
                matched_text=result.get("title"),
            )

    # Tier 2: Brand or title match
    for result in results:
        result_title = (result.get("title") or "").lower()
        result_body = (result.get("body") or "").lower()

        if brand and brand in result_title:
            return SearchPresence(
                status="brand_visible",
                score=_SCORE_BRAND_IN_TITLE,
                found_url=result.get("href"),
                matched_text=result.get("title"),
            )
        if brand and brand in result_body:
            return SearchPresence(
                status="brand_visible",
                score=_SCORE_BRAND_IN_SNIPPET,
                found_url=result.get("href"),
                matched_text=result.get("title"),
            )
        if title_tokens:
            result_combined = result_title + " " + result_body
            result_tokens = set(re.findall(r"[a-z]{3,}", result_combined))
            overlap = title_tokens & result_tokens
            if len(overlap) >= _MIN_TITLE_WORD_OVERLAP:
                return SearchPresence(
                    status="brand_visible",
                    score=_SCORE_PARTIAL_TITLE_MATCH,
                    found_url=result.get("href"),
                    matched_text=result.get("title"),
                )

    # Tier 3: Domain presence
    if domain:
        for result in results:
            result_href = (result.get("href") or "").lower()
            if domain in result_href:
                return SearchPresence(
                    status="not_visible",
                    score=_SCORE_DOMAIN_PRESENT,
                    found_url=result.get("href"),
                    matched_text=result.get("title"),
                )

    # Tier 4: No presence
    return SearchPresence(
        status="not_visible",
        score=_SCORE_NOT_VISIBLE,
        found_url=None,
        matched_text=None,
    )


# ===========================================================================
# Main public function
# ===========================================================================


def check_search_presence(
    url: str,
    brand_name: Optional[str] = None,
    page_title: Optional[str] = None,
) -> SearchPresence:
    """
    Validate whether a page or brand is visible in DuckDuckGo search results.

    Checks cache first. Performs at most one live search per call.
    All failures return a safe SearchPresence — never raises.

    Parameters
    ----------
    url : str
    brand_name : Optional[str]
    page_title : Optional[str]
    Returns
    -------
    SearchPresence
    """
    brand = _sanitise_brand(url, brand_name)
    query = infer_query(url, brand_name, page_title)

    try:
        results = run_search(query)
    except Exception:
        results = []

    if not results:
        return SearchPresence(
            status="not_visible",
            score=_SCORE_NOT_VISIBLE,
            found_url=None,
            matched_text="Search data unavailable",
        )

    return score_results(results=results, url=url, brand=brand, page_title=page_title)


# ===========================================================================
# Phase 2 — Prompt presence check
# ===========================================================================


def check_prompt_presence(
    url: str,
    domain: str,
    prompt: str,
) -> PromptPresenceResult:
    """
    Run a DuckDuckGo search for a specific keyword prompt and check whether
    the target URL or domain appears in the results.

    Uses the same three-tier logic as check_search_presence() but is
    prompt-specific rather than brand/title-driven. Results are cached.

    Parameters
    ----------
    url : str
        The audited page URL (used for exact-match check).
    domain : str
        Full domain string (e.g. "ahrefs.com") for domain-level match.
    prompt : str
        The natural language query to test (e.g. "best tools for GEO").

    Returns
    -------
    PromptPresenceResult
        visibility: "exact_match" | "brand_visible" | "not_visible"
        competitor_url: first result URL if user's page is not found
        search_position: 1-based position in results where match was found
    """
    if not prompt or not prompt.strip():
        return PromptPresenceResult(
            prompt=prompt,
            visibility="not_visible",
            competitor_url=None,
            search_position=None,
        )

    results = run_search(prompt.strip())

    if not results:
        return PromptPresenceResult(
            prompt=prompt,
            visibility="not_visible",
            competitor_url=None,
            search_position=None,
        )

    normalised_url = url.rstrip("/").lower()
    domain_lower = domain.lower().lstrip("www.") if domain else ""

    # Walk results in rank order
    for position, result in enumerate(results, start=1):
        href = (result.get("href") or "").rstrip("/").lower()

        # Exact URL match
        if href == normalised_url:
            return PromptPresenceResult(
                prompt=prompt,
                visibility="exact_match",
                competitor_url=None,
                search_position=position,
            )

        # Domain-level match
        if domain_lower and domain_lower in href:
            return PromptPresenceResult(
                prompt=prompt,
                visibility="brand_visible",
                competitor_url=None,
                search_position=position,
            )

    # Not found — return the top result as the competitor that took the spot
    top_competitor = results[0].get("href") if results else None

    return PromptPresenceResult(
        prompt=prompt,
        visibility="not_visible",
        competitor_url=top_competitor,
        search_position=None,
    )