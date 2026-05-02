"""
services/heuristic_service.py
==============================
Deterministic heuristic fallback for the AiGeoPacific AI Citation Analyser.

Responsibilities:
- Generate a fully populated EnrichmentResult using pure Python logic
- Serve as the guaranteed fallback when Gemini is unavailable, rate-limited,
  or returns an unparseable response
- Mirror the public interface of gemini_service.py so the audit runner and
  app.py can swap services without changing call sites

This module makes zero network calls, uses no LLMs, and never crashes.
It always returns a valid EnrichmentResult Pydantic object.

Allowed imports: random, typing, core.models only.
"""

import random
from typing import Dict, List, Optional
from urllib.parse import urlparse

from core.models import EnrichmentResult, MetricScore

# ---------------------------------------------------------------------------
# Score band thresholds
# ---------------------------------------------------------------------------

_BAND_LOW: float = 45.0
_BAND_MED: float = 70.0

# ---------------------------------------------------------------------------
# Professional phrase pools — add variety without LLM calls
# ---------------------------------------------------------------------------

_IMPACT_OPENERS: List[str] = [
    "This analysis indicates",
    "Our audit suggests",
    "The current citation signals show",
    "The evaluation reveals",
    "Based on the audit data",
    "The citation readiness assessment shows",
]

_IMPACT_TRANSITIONS: List[str] = [
    "As a result,",
    "Consequently,",
    "This means",
    "In practical terms,",
    "The implication is that",
]

_IDEAL_TARGETS: Dict[str, float] = {
    "target_cqs": 85.0,
    "recommended_word_count": 1200.0,
    "external_link_percentage": 3.5,
    "minimum_sources": 5.0,
}


# ===========================================================================
# Helper — URL topic extraction
# ===========================================================================


def _topic_from_url(url: str) -> str:
    """
    Derive a readable topic string from the URL slug.

    Used to make suggested search prompts feel page-specific even
    without keyword data.

    Parameters
    ----------
    url : str
        The audited page URL.

    Returns
    -------
    str
        A space-separated topic phrase, e.g. "ai seo guide".
        Falls back to "this topic" if the path yields nothing useful.
    """
    try:
        path = urlparse(url).path or ""
        segments = [s for s in path.split("/") if s]
        if not segments:
            return "this topic"
        slug = segments[-1]
        # Strip file extension and replace separators
        slug = slug.rsplit(".", 1)[0]
        topic = slug.replace("-", " ").replace("_", " ").strip().lower()
        return topic if len(topic) > 3 else "this topic"
    except Exception:
        return "this topic"


# ===========================================================================
# 1 — Business Impact
# ===========================================================================


def _generate_business_impact(cqs: float) -> str:
    """
    Generate a professional paragraph explaining the business impact of
    the current CQS score on AI citation visibility.

    Three distinct narratives are used for low / medium / high bands.
    random.choice() selects from phrase lists to reduce robotic repetition.

    Parameters
    ----------
    cqs : float
        The Citation Quality Score (0-100).

    Returns
    -------
    str
        A two-to-three sentence business impact paragraph.
    """
    opener = random.choice(_IMPACT_OPENERS)
    transition = random.choice(_IMPACT_TRANSITIONS)

    if cqs < _BAND_LOW:
        return (
            f"{opener} that this page has critical weaknesses in AI citation readiness "
            f"with a Citation Quality Score of {cqs:.0f}/100. "
            f"{transition} AI systems such as ChatGPT, Perplexity, and Google AI Overviews "
            f"are unlikely to surface this content in AI-generated answers, leaving "
            f"competitors to capture that traffic instead. "
            f"Immediate structural improvements are required to establish the trust and "
            f"authority signals that AI citation engines require."
        )
    elif cqs < _BAND_MED:
        return (
            f"{opener} that this page has a moderate AI citation readiness score of "
            f"{cqs:.0f}/100, indicating a partial citation gap. "
            f"{transition} the page may appear in some AI Overviews but is likely being "
            f"outcompeted by pages with stronger entity density, structured data, and "
            f"authoritative outbound references. "
            f"Targeted improvements to the weakest signals will meaningfully increase "
            f"citation frequency across major AI platforms."
        )
    else:
        return (
            f"{opener} that this page is a strong candidate for AI citation with a "
            f"Citation Quality Score of {cqs:.0f}/100. "
            f"{transition} the content is well-positioned to appear in AI-generated "
            f"answers, though secondary signals such as schema markup and claim support "
            f"can still be optimised to increase citation consistency across all major "
            f"AI systems including ChatGPT, Perplexity, and Google AI Overviews."
        )


# ===========================================================================
# 2 — Quick Wins
# ===========================================================================


def _generate_quick_wins(metric_scores: List[MetricScore]) -> List[str]:
    """
    Identify the 3 lowest-scoring metrics and return their what_to_fix
    text as quick-win action strings.

    Parameters
    ----------
    metric_scores : List[MetricScore]
        All scored metrics from the primary audit.

    Returns
    -------
    List[str]
        Up to 3 quick-win strings. Returns generic fallbacks if metrics
        are absent or malformed.
    """
    if not metric_scores:
        return [
            "Ensure the page can be fully crawled and indexed by search engines.",
            "Add structured data (JSON-LD) to communicate page intent to AI systems.",
            "Include at least three outbound links to authoritative external sources.",
        ]

    # Sort ascending by score — lowest first
    try:
        sorted_metrics = sorted(metric_scores, key=lambda m: m.score)
    except Exception:
        sorted_metrics = metric_scores

    quick_wins: List[str] = []
    for metric in sorted_metrics[:3]:
        try:
            fix_text = metric.what_to_fix or f"Improve {metric.name} score."
            quick_wins.append(fix_text)
        except Exception:
            quick_wins.append("Review and improve page content structure.")

    return quick_wins if quick_wins else [
        "Restructure content to answer the target query in the opening paragraph.",
        "Add FAQ schema to increase structured data coverage.",
        "Include citations and outbound links to authoritative sources.",
    ]


# ===========================================================================
# 3 — Recommendations
# ===========================================================================


def _generate_recommendations(metric_scores: List[MetricScore]) -> List[Dict[str, str]]:
    """
    Generate prioritised fix recommendations from metric scores.

    Priority mapping:
    - score < 40   → 🔥 High Priority
    - score 40–70  → ⚙️ Medium Priority
    - score > 70   → 🚀 Long-Term Optimization

    Capped at 8 recommendations, sorted high-priority first.

    Parameters
    ----------
    metric_scores : List[MetricScore]
        All scored metrics.

    Returns
    -------
    List[Dict[str, str]]
        List of dicts with "priority" and "action" keys.
    """
    if not metric_scores:
        return [
            {"priority": "🔥", "action": "Fetch the page and run a full audit before acting on recommendations."},
        ]

    recommendations: List[Dict[str, str]] = []

    try:
        sorted_metrics = sorted(metric_scores, key=lambda m: m.score)
    except Exception:
        sorted_metrics = metric_scores

    for metric in sorted_metrics:
        try:
            score = metric.score
            action = metric.what_to_fix or f"Improve {metric.name}."

            if score < 40.0:
                priority = "🔥"
            elif score <= 70.0:
                priority = "⚙️"
            else:
                priority = "🚀"

            recommendations.append({"priority": priority, "action": action})
        except Exception:
            continue

    return recommendations[:8]


# ===========================================================================
# 4 — Ideal Targets (static benchmarks)
# ===========================================================================


def _generate_ideal_targets() -> Dict[str, float]:
    """
    Return deterministic SEO benchmarks representing strong AI citation
    readiness. These are static values — not derived from page content.

    Returns
    -------
    Dict[str, float]
        Benchmark targets for CQS, word count, link percentage, and sources.
    """
    return dict(_IDEAL_TARGETS)


# ===========================================================================
# 5 — Competitor Insight
# ===========================================================================


def _generate_competitor_insight(competitor_comparison) -> List[str]:
    """
    Generate a plain-English paragraph about why competitors outperform
    the user's page, derived from the competitor_comparison data.

    Falls back to a generic observation if no competitor data is present.

    Parameters
    ----------
    competitor_comparison : dict or CompetitorComparison
        Competitor data from the audit pipeline.

    Returns
    -------
    List[str]
        One-item list containing the insight paragraph (matches
        EnrichmentResult.competitor_insight: List[str] type).
    """
    gaps: List[str] = []
    competitor_count: int = 0

    try:
        if isinstance(competitor_comparison, dict):
            gaps = competitor_comparison.get("gaps", [])
            competitor_count = len(competitor_comparison.get("competitors", []))
        else:
            gaps = getattr(competitor_comparison, "gaps", [])
            competitors = getattr(competitor_comparison, "competitors", [])
            competitor_count = len(competitors)
    except Exception:
        pass

    if not competitor_count and not gaps:
        return [
            "Competitor data was not available for this audit. "
            "In general, pages that rank highly for AI citation tend to feature "
            "authoritative outbound links, clear heading structure, structured schema data, "
            "and direct answers to common queries in their opening paragraphs."
        ]

    gap_summary = ""
    if gaps:
        # Use the first meaningful gap as the core of the insight
        gap_summary = f" Key gaps identified include: {gaps[0].rstrip('.')}."

    return [
        f"Analysis of {competitor_count} competitor page(s) reveals structural and "
        f"authority differences that contribute to their stronger AI citation signals.{gap_summary} "
        f"Competitor pages typically score higher on Link Authority and Formatting Readiness, "
        f"suggesting they invest more in external citations and structured content organisation. "
        f"Closing these gaps should be the primary focus for improving AI citation frequency."
    ]


# ===========================================================================
# 6 — LLM Key Signals
# ===========================================================================


def _generate_llm_key_signals(cqs: float) -> Dict[str, str]:
    """
    Generate brief per-LLM interpretations of what the CQS score means
    for citation likelihood on each major AI platform.

    Parameters
    ----------
    cqs : float
        The Citation Quality Score (0-100).

    Returns
    -------
    Dict[str, str]
        Keys: "chatgpt", "perplexity", "claude". Values: one-sentence summaries.
    """
    if cqs < _BAND_LOW:
        return {
            "chatgpt": (
                "Content signals are too weak for reliable ChatGPT citation; "
                "structural improvements are needed before this page will be surfaced."
            ),
            "perplexity": (
                "Perplexity is unlikely to cite this page given its low authority and "
                "formatting signals — adding structured data and outbound links is the priority."
            ),
            "claude": (
                "Low entity density and limited claim support reduce the likelihood of "
                "Claude citing this page in research-style responses."
            ),
        }
    elif cqs < _BAND_MED:
        return {
            "chatgpt": (
                "Partial eligibility for ChatGPT citation — the page has moderate signals "
                "but inconsistent formatting and authority references limit reliability."
            ),
            "perplexity": (
                "Perplexity may occasionally reference this page but stronger outbound "
                "citations and FAQ schema would significantly improve citation frequency."
            ),
            "claude": (
                "Moderate citation potential for Claude; improving claim support and "
                "BLUF clarity would help surface this page in direct-answer contexts."
            ),
        }
    else:
        return {
            "chatgpt": (
                "Strong candidate for ChatGPT citation — the page demonstrates clear "
                "entity density, structured formatting, and authoritative source linking."
            ),
            "perplexity": (
                "This page is well-positioned for Perplexity citation; maintaining "
                "current authority signals and adding FAQ schema will reinforce visibility."
            ),
            "claude": (
                "High citation potential for Claude, particularly in research and "
                "comparison queries where claim support and readability are prioritised."
            ),
        }


# ===========================================================================
# 7 — Suggested Search Prompts
# ===========================================================================


def _generate_suggested_search_prompts(url: str) -> List[str]:
    """
    Generate 6 natural-language search queries the page should target.

    Prompts are derived from the URL topic slug and standard AI-search
    query patterns. They are intentionally generic enough to apply to
    any page while remaining directionally useful.

    Parameters
    ----------
    url : str
        The audited page URL.

    Returns
    -------
    List[str]
        Exactly 6 search query strings.
    """
    topic = _topic_from_url(url)
    t = topic  # short alias for readability in f-strings

    return [
        f"What is the best way to understand {t}?",
        f"How does {t} work and why does it matter?",
        f"What are the most important factors for {t}?",
        f"How can I improve my results with {t}?",
        f"What do experts recommend for {t}?",
        f"What are common mistakes to avoid with {t}?",
    ]


# ===========================================================================
# Main public function
# ===========================================================================


def generate_enrichment(audit_data: dict) -> EnrichmentResult:
    """
    Generate deterministic AI citation insights using pure heuristic logic.

    This function mirrors the public interface of gemini_service.generate_enrichment()
    so the audit runner and app.py can switch between services transparently.

    All sub-generators handle missing or malformed data safely — this
    function will always return a valid EnrichmentResult regardless of
    what audit_data contains.

    Parameters
    ----------
    audit_data : dict
        Expected keys: url, text, cqs, metric_scores, competitor_comparison.
        All keys are treated as optional — missing values produce safe fallbacks.

    Returns
    -------
    EnrichmentResult
        Fully populated EnrichmentResult Pydantic model.
    """
    # Safely extract all inputs
    url: str = audit_data.get("url") or ""
    cqs_raw = audit_data.get("cqs", 0)
    try:
        cqs = float(cqs_raw)
    except (TypeError, ValueError):
        cqs = 0.0

    # metric_scores may be a list of Pydantic objects or dicts
    raw_metrics = audit_data.get("metric_scores") or []
    metric_scores: List[MetricScore] = []
    for m in raw_metrics:
        if isinstance(m, MetricScore):
            metric_scores.append(m)
        elif isinstance(m, dict):
            try:
                metric_scores.append(MetricScore(**m))
            except Exception:
                pass

    competitor_comparison = audit_data.get("competitor_comparison") or {}

    # Generate each enrichment component
    business_impact = _generate_business_impact(cqs)
    quick_wins = _generate_quick_wins(metric_scores)
    recommendations = _generate_recommendations(metric_scores)
    ideal_targets = _generate_ideal_targets()
    competitor_insight = _generate_competitor_insight(competitor_comparison)
    llm_key_signals = _generate_llm_key_signals(cqs)
    suggested_search_prompts = _generate_suggested_search_prompts(url)

    return EnrichmentResult(
        business_impact=business_impact,
        quick_wins=quick_wins,
        recommendations=recommendations,
        ideal_targets=ideal_targets,
        competitor_insight=competitor_insight,
        llm_key_signals=llm_key_signals,
        suggested_search_prompts=suggested_search_prompts,
    )