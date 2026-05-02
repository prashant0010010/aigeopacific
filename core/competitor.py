"""
core/competitor.py
==================
Competitor Analysis module for the AiGeoPacific AI Citation Analyser.

Phase 2 additions:
- Concurrent competitor fetching via ThreadPoolExecutor (max_workers=3)
- Per-URL timeout of 15 seconds; total competitor block timeout of 30 seconds
- Citation-anchored gap analysis: gap text references specific competitor
  advantages where citation patterns differ

This module never crashes the audit pipeline.
All competitor fetch/score failures are caught silently and partial results
are returned.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Dict, List, Optional
from urllib.parse import urlparse

from core.fetcher import fetch_page
from core.models import (
    CompetitorComparison,
    CompetitorMetric,
    MetricScore,
    PageConfig,
)
from core.scorer import compute_cqs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Giant domains — excluded from competitor selection
# ---------------------------------------------------------------------------

GIANT_DOMAINS: List[str] = [
    "wikipedia.org",
    "amazon.com",
    "facebook.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "pinterest.com",
    "linkedin.com",
    "reddit.com",
]

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_MAX_RESULTS_TO_SCAN: int = 10
_MAX_COMPETITORS: int = 3
_GAP_THRESHOLD: float = 15.0
_MAX_GAP_INSIGHTS: int = 5
_MAX_WINNING_FACTORS: int = 3

# Phase 2 concurrency settings
_MAX_WORKERS: int = 3
_TOTAL_TIMEOUT: int = 30      # seconds for all competitor fetches combined
_PER_URL_TIMEOUT: int = 15    # seconds per individual fetch (enforced in fetch_page)


# ===========================================================================
# URL / domain helpers
# ===========================================================================


def extract_domain(url: str) -> str:
    """
    Extract the bare hostname from a URL, stripping leading 'www.'.

    Parameters
    ----------
    url : str
    Returns
    -------
    str
        Lowercase hostname (e.g. "example.com"), or empty string on failure.
    """
    try:
        hostname = urlparse(url).hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception:
        return ""


def is_giant_domain(domain: str) -> bool:
    """
    Return True if the domain matches any entry in GIANT_DOMAINS.

    Uses suffix matching so subdomains of giants are also excluded.
    """
    for giant in GIANT_DOMAINS:
        if domain == giant or domain.endswith("." + giant):
            return True
    return False


# ===========================================================================
# Competitor selection
# ===========================================================================


def select_competitors(
    search_results: List[dict],
    user_domain: str,
) -> List[str]:
    """
    Filter search results and return up to 3 valid competitor URLs.

    Selection rules (applied in order):
    1. Skip results whose domain matches the user's own domain.
    2. Skip results whose domain is in GIANT_DOMAINS.
    3. Stop after collecting 3 valid URLs or exhausting the first 10 results.

    Parameters
    ----------
    search_results : List[dict]
    user_domain : str
    Returns
    -------
    List[str]
    """
    selected: List[str] = []
    scanned: int = 0

    for result in search_results:
        if scanned >= _MAX_RESULTS_TO_SCAN:
            break
        scanned += 1

        href = result.get("href") or ""
        if not href.startswith("http"):
            continue

        domain = extract_domain(href)
        if not domain:
            continue

        if user_domain and domain == user_domain:
            continue

        if is_giant_domain(domain):
            continue

        selected.append(href)

        if len(selected) >= _MAX_COMPETITORS:
            break

    return selected


# ===========================================================================
# Competitor mini-audit (single URL — called in thread)
# ===========================================================================


def _audit_single_competitor(url: str) -> Optional[CompetitorMetric]:
    """
    Fetch and score a single competitor page. Intended to run inside a
    ThreadPoolExecutor worker thread.

    Returns None silently on any failure (fetch error, JS gate, exception).

    Parameters
    ----------
    url : str
    Returns
    -------
    Optional[CompetitorMetric]
    """
    try:
        page_data = fetch_page(url)

        if page_data.get("status") in ("failed", "limited_access"):
            return None

        competitor_config = PageConfig(
            url=url,
            target_keyword=None,
            brand_name=None,
        )

        metric_scores, cqs, _ = compute_cqs(
            page_config=competitor_config,
            page_data=page_data,
            search_presence=0.0,
        )

        metrics_dict: Dict[str, float] = {
            m.name: m.score for m in metric_scores
        }

        return CompetitorMetric(
            competitor_url=url,
            metrics=metrics_dict,
            cqs=cqs,
        )

    except Exception as exc:
        logger.debug("Competitor audit failed for %s: %s", url, exc)
        return None


# ===========================================================================
# Concurrent competitor fetching (Phase 2)
# ===========================================================================


def fetch_and_score_competitors(
    urls: List[str],
) -> List[CompetitorMetric]:
    """
    Run mini-audits on all competitor URLs concurrently using
    ThreadPoolExecutor.

    Note: Uses concurrent.futures, NOT asyncio. Streamlit has known event
    loop conflicts with asyncio — ThreadPoolExecutor is safe in all
    Streamlit versions.

    Per-URL timeout: _PER_URL_TIMEOUT (15 seconds) enforced by fetcher.
    Total block timeout: _TOTAL_TIMEOUT (30 seconds) via as_completed().

    Parameters
    ----------
    urls : List[str]
        Competitor URLs selected by select_competitors().

    Returns
    -------
    List[CompetitorMetric]
        Successfully audited competitors. May be shorter than input if
        some URLs timed out or failed.
    """
    if not urls:
        return []

    audited: List[CompetitorMetric] = []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_to_url = {
            executor.submit(_audit_single_competitor, url): url
            for url in urls
        }

        try:
            for future in as_completed(future_to_url, timeout=_TOTAL_TIMEOUT):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result is not None:
                        audited.append(result)
                        logger.debug("Competitor audited: %s (CQS %.1f)", url, result.cqs)
                    else:
                        logger.debug("Competitor skipped (no result): %s", url)
                except Exception as exc:
                    logger.debug("Competitor future failed for %s: %s", url, exc)

        except FuturesTimeoutError:
            logger.warning(
                "Competitor fetch block exceeded %ds timeout. "
                "%d/%d results collected.",
                _TOTAL_TIMEOUT, len(audited), len(urls)
            )

    return audited


# ===========================================================================
# Gap analysis
# ===========================================================================


def generate_gap_analysis(
    user_metrics: List[MetricScore],
    competitor_results: List[CompetitorMetric],
) -> tuple:
    """
    Compare user metric scores against competitor averages and produce
    human-readable gap insights and winning factor statements.

    Phase 2: gap text is citation-anchored where relevant, naming the
    specific competitor behaviour that drives the delta.

    Only generates a gap entry when the average delta exceeds
    _GAP_THRESHOLD (15 points). Limits to _MAX_GAP_INSIGHTS gaps and
    _MAX_WINNING_FACTORS wins.

    Parameters
    ----------
    user_metrics : List[MetricScore]
    competitor_results : List[CompetitorMetric]
    Returns
    -------
    tuple
        (gaps: List[str], winning_factors: List[str])
    """
    if not competitor_results or not user_metrics:
        return [], []

    user_scores: Dict[str, float] = {m.name: m.score for m in user_metrics}
    all_metric_names = list(user_scores.keys())
    avg_competitor: Dict[str, float] = {}

    for metric_name in all_metric_names:
        scores = [
            c.metrics.get(metric_name, 0.0)
            for c in competitor_results
            if metric_name in c.metrics
        ]
        avg_competitor[metric_name] = sum(scores) / len(scores) if scores else 0.0

    # Citation-anchored gap templates (Phase 2)
    gap_templates: Dict[str, str] = {
        "BLUF Score": (
            "Competitor pages answer the core query in the first sentence. "
            "AI systems extract that answer and cite the source directly. "
            "Move your key answer to the opening paragraph."
        ),
        "Entity Density": (
            "Competitor pages name specific organisations, dates, and statistics "
            "that AI citation systems treat as credibility anchors. "
            "Add named entities and concrete data points to your content."
        ),
        "Link Authority": (
            "Competitor pages cite .gov, .edu, and major publication sources "
            "that AI systems weight as high-trust references. "
            "Add outbound citations to authoritative sources near key claims."
        ),
        "Formatting Readiness": (
            "Competitor pages use H2/H3 headings and bullet lists that AI "
            "parsers can extract as structured answers. "
            "Restructure your content with clear heading hierarchy and lists."
        ),
        "Schema Presence": (
            "Competitor pages implement JSON-LD or FAQ schema that AI systems "
            "read as machine-verified content signals. "
            "Add Article or FAQPage schema markup to your page."
        ),
        "Claim Support": (
            "Competitor pages attribute claims to named sources inline. "
            "AI systems prefer content where assertions are verifiable. "
            "Add inline citations or attribution phrases after key statistics."
        ),
        "Readability": (
            "Competitor pages use shorter sentences that AI parsers reproduce "
            "without compression errors. "
            "Target an average sentence length below 18 words."
        ),
        "Search Presence": (
            "Your page has lower search visibility than the competitors analysed. "
            "Pages that do not appear in search results are rarely indexed for "
            "AI citation. Focus on internal linking and backlink acquisition."
        ),
    }

    winning_templates: Dict[str, str] = {
        "BLUF Score": (
            "Your page answers the query faster than most competitors — "
            "a strong signal for AI extraction and direct citation."
        ),
        "Entity Density": (
            "Your page contains more specific entities than competing pages, "
            "signalling stronger factual authority to AI citation systems."
        ),
        "Link Authority": (
            "Your page cites more authoritative sources than competitors, "
            "increasing its trust score in AI retrieval pipelines."
        ),
        "Formatting Readiness": (
            "Your page is better structured than competing pages, "
            "making it easier for AI systems to parse and cite."
        ),
        "Schema Presence": (
            "Your page implements richer structured data than competitors, "
            "improving machine-readability for AI crawlers."
        ),
        "Claim Support": (
            "Your page backs its claims with more citations than competitor pages, "
            "making your content a preferred AI source."
        ),
        "Readability": (
            "Your page is easier to read than competing pages, "
            "reducing parsing ambiguity for AI systems."
        ),
        "Search Presence": (
            "Your page has stronger search visibility than the competitors analysed, "
            "improving your baseline AI discoverability."
        ),
    }

    gaps: List[str] = []
    winning_factors: List[str] = []

    deltas = []
    for metric_name in all_metric_names:
        user_score = user_scores.get(metric_name, 0.0)
        avg_comp = avg_competitor.get(metric_name, 0.0)
        delta = avg_comp - user_score
        deltas.append((metric_name, delta, user_score, avg_comp))

    deltas.sort(key=lambda x: abs(x[1]), reverse=True)

    for metric_name, delta, user_score, avg_comp in deltas:
        if abs(delta) < _GAP_THRESHOLD:
            continue

        if delta > 0 and len(gaps) < _MAX_GAP_INSIGHTS:
            template = gap_templates.get(metric_name)
            if template:
                gaps.append(
                    f"{template} "
                    f"(Your score: {user_score:.0f} | Competitor avg: {avg_comp:.0f})"
                )

        elif delta < 0 and len(winning_factors) < _MAX_WINNING_FACTORS:
            template = winning_templates.get(metric_name)
            if template:
                winning_factors.append(
                    f"{template} "
                    f"(Your score: {user_score:.0f} | Competitor avg: {avg_comp:.0f})"
                )

        if len(gaps) >= _MAX_GAP_INSIGHTS and len(winning_factors) >= _MAX_WINNING_FACTORS:
            break

    return gaps, winning_factors


# ===========================================================================
# Main public function
# ===========================================================================


def analyze_competitors(
    search_results: List[dict],
    user_metrics: List[MetricScore],
    page_config: PageConfig,
) -> CompetitorComparison:
    """
    Identify top competitors from search results, run concurrent mini-audits,
    and return a CompetitorComparison with citation-anchored gap insights.

    Phase 2: competitor fetching is concurrent (ThreadPoolExecutor, 3 workers)
    rather than sequential, reducing wall-clock time from ~45s to ~15s.

    Parameters
    ----------
    search_results : List[dict]
    user_metrics : List[MetricScore]
    page_config : PageConfig
    Returns
    -------
    CompetitorComparison
    """
    user_domain = extract_domain(page_config.url)
    competitor_urls = select_competitors(search_results, user_domain)

    if not competitor_urls:
        return CompetitorComparison(
            competitors=[],
            gaps=["No suitable competitor pages were found in search results."],
        )

    # Phase 2: concurrent fetch replaces sequential loop
    audited = fetch_and_score_competitors(competitor_urls)

    if not audited:
        return CompetitorComparison(
            competitors=[],
            gaps=["Competitor pages could not be fetched or analyzed."],
        )

    gaps, winning_factors = generate_gap_analysis(user_metrics, audited)
    all_insights = gaps + winning_factors

    return CompetitorComparison(
        competitors=audited,
        gaps=all_insights if all_insights else [
            "Competitor scores are similar to yours. "
            "Focus on Search Presence and Schema for the highest citation lift."
        ],
    )