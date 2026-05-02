"""
core/scorer.py
==============
Deterministic scoring engine for the AiGeoPacific AI Citation Analyser.

Responsibilities:
- Accept a PageConfig, a fetcher result dict, and a search_presence float
- Score the page across 8 GEO metrics using only heuristics, regex, and
  simple statistical logic — no LLMs, no external APIs, no ML
- Return a list of MetricScore Pydantic objects and a final CQS float

This module is the core intelligence of the product. It must be:
- Fast: no heavy computation or blocking calls
- Deterministic: identical input always produces identical output
- Safe: never crashes regardless of content quality or fetch status

Allowed imports: re, math, bs4 (limited), core.models only.
"""

import math
import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from core.models import MetricScore, PageConfig

# ---------------------------------------------------------------------------
# Metric weights — must sum to 1.0
# ---------------------------------------------------------------------------

WEIGHTS: Dict[str, float] = {
    "BLUF Score":           0.15,
    "Link Authority":       0.15,
    "Search Presence":      0.14,
    "Entity Density":       0.12,
    "Formatting Readiness": 0.12,
    "Claim Support":        0.12,
    "Schema Presence":      0.10,
    "Readability":          0.10,
}

# ---------------------------------------------------------------------------
# Authority domain list for Link Authority scoring
# ---------------------------------------------------------------------------

_AUTHORITY_DOMAINS: Tuple[str, ...] = (
    ".gov", ".edu",
    "bbc.com", "bbc.co.uk",
    "nytimes.com", "reuters.com", "apnews.com",
    "theguardian.com", "washingtonpost.com",
    "nature.com", "sciencemag.org", "pubmed.ncbi.nlm.nih.gov",
    "who.int", "un.org", "worldbank.org",
    "forbes.com", "bloomberg.com", "ft.com",
    "wsj.com", "economist.com",
    "harvard.edu", "mit.edu", "stanford.edu",
    "wikipedia.org",
)

# ---------------------------------------------------------------------------
# Penalty multiplier for limited_access pages
# ---------------------------------------------------------------------------

_LIMITED_ACCESS_MULTIPLIER: float = 0.60  # 40% reduction


# ===========================================================================
# Metric scorers
# ===========================================================================


def _score_bluf(text: str, keyword: Optional[str], title: str) -> float:
    """
    BLUF (Bottom Line Up Front) Score — 15%.

    Measures whether the page delivers its core answer early.
    Analyses the first 300 words (or first 10% of text, whichever is
    smaller) for overlap with the inferred topic.

    Scoring:
    - 80–100: keyword or strong title-word overlap found in first paragraph
    - 50–79: partial topic words present in early text
    - 0–49:  topic absent from opening section

    Parameters
    ----------
    text : str
        Full cleaned page text.
    keyword : Optional[str]
        Explicit target keyword from PageConfig, may be None.
    title : str
        Page title, used as topic proxy when keyword is absent.

    Returns
    -------
    float
        Score 0–100.
    """
    if not text:
        return 0.0

    words = text.split()
    total_words = len(words)
    if total_words == 0:
        return 0.0

    window = min(300, max(1, int(total_words * 0.10)))
    opening = " ".join(words[:window]).lower()

    # Build topic tokens from keyword or title
    topic_source = keyword if keyword else title
    if not topic_source:
        # No topic signal — reward any structured opening paragraph
        sentences = re.split(r"[.!?]", opening)
        return 60.0 if len(sentences) >= 2 else 30.0

    topic_tokens = set(re.findall(r"[a-z]{3,}", topic_source.lower()))
    if not topic_tokens:
        return 40.0

    opening_tokens = set(re.findall(r"[a-z]{3,}", opening))
    overlap = topic_tokens & opening_tokens
    ratio = len(overlap) / len(topic_tokens)

    if ratio >= 0.75:
        return 90.0
    elif ratio >= 0.40:
        # Scale 50–79 based on ratio within 0.40–0.74
        return 50.0 + ((ratio - 0.40) / 0.35) * 29.0
    elif ratio > 0.0:
        return 25.0 + ratio * 60.0
    else:
        return 10.0


def _score_entity_density(text: str) -> float:
    """
    Entity Density Score — 12%.

    Measures how rich the page is in named entities: proper nouns,
    numbers, dates, and specific data points. Higher entity density
    signals factual, authoritative content to AI systems.

    Heuristic: counts capitalised words that do NOT start a sentence
    (proxy for proper nouns), plus numeric/date patterns, normalised
    against total word count.

    Parameters
    ----------
    text : str
        Full cleaned page text.

    Returns
    -------
    float
        Score 0–100.
    """
    if not text:
        return 0.0

    words = text.split()
    total = len(words)
    if total < 10:
        return 0.0

    # Detect sentence-start positions to exclude normal capitalisation
    sentence_starts: set = set()
    for m in re.finditer(r"(?:^|[.!?]\s+)([A-Z])", text):
        # Mark the word index nearest this match — approximate
        preceding_text = text[:m.start()]
        sentence_starts.add(len(preceding_text.split()))

    proper_noun_count = 0
    for i, word in enumerate(words):
        if i in sentence_starts:
            continue
        clean = re.sub(r"[^A-Za-z]", "", word)
        if clean and clean[0].isupper() and len(clean) > 1:
            proper_noun_count += 1

    # Numeric and date patterns
    numeric_count = len(re.findall(
        r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b"          # numbers / percentages
        r"|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"  # month names
        r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?"
        r"|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},?\s+\d{4}\b"
        r"|\b\d{4}\b",                                   # standalone years
        text
    ))

    entity_count = proper_noun_count + numeric_count
    density = entity_count / total  # ratio per word

    # Calibration: 0.05 density ≈ score 50, 0.15+ ≈ score 100
    raw = (density / 0.15) * 100.0
    return min(100.0, max(0.0, raw))


def _score_link_authority(html: Optional[str]) -> float:
    """
    Link Authority Score — 15%.

    Evaluates the quality and quantity of outbound links.
    Pages that cite high-authority sources (.gov, .edu, major publications)
    signal to AI systems that their claims are grounded in credible evidence.

    Scoring bands:
    - No links at all:                     5–20
    - Links present but none authoritative: 20–40
    - Some authoritative links:            40–70
    - Multiple high-quality authority links: 70–100

    Parameters
    ----------
    html : Optional[str]
        Raw HTML. If None, returns 0.

    Returns
    -------
    float
        Score 0–100.
    """
    if not html:
        return 0.0

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    external_links = [
        a["href"] for a in anchors
        if a["href"].startswith("http") and not a["href"].startswith("javascript")
    ]

    total_external = len(external_links)
    if total_external == 0:
        return 10.0

    authority_count = sum(
        1 for link in external_links
        if any(domain in link.lower() for domain in _AUTHORITY_DOMAINS)
    )

    if authority_count == 0:
        # Has links but none authoritative
        base = min(35.0, 20.0 + total_external * 1.5)
        return base

    # Authority ratio — blend raw count with proportion
    authority_ratio = authority_count / max(total_external, 1)
    count_bonus = min(20.0, authority_count * 5.0)  # up to +20 for volume
    ratio_score = authority_ratio * 60.0             # up to 60 for 100% authority
    score = 40.0 + ratio_score + count_bonus
    return min(100.0, score)


def _score_formatting_readiness(html: Optional[str], text: str) -> float:
    """
    Formatting Readiness Score — 12%.

    Checks whether the page uses structural HTML elements that help
    AI systems parse and extract information cleanly. Headers, lists,
    and logical sectioning make content far more citable.

    Parameters
    ----------
    html : Optional[str]
        Raw HTML for tag-level checks.
    text : str
        Cleaned text as fallback for structure heuristics.

    Returns
    -------
    float
        Score 0–100.
    """
    score = 0.0

    if html:
        soup = BeautifulSoup(html, "html.parser")

        h2_count = len(soup.find_all("h2"))
        h3_count = len(soup.find_all("h3"))
        ul_count = len(soup.find_all("ul"))
        ol_count = len(soup.find_all("ol"))
        table_count = len(soup.find_all("table"))
        blockquote_count = len(soup.find_all("blockquote"))

        # Headings
        if h2_count >= 3:
            score += 30.0
        elif h2_count >= 1:
            score += 15.0

        if h3_count >= 2:
            score += 15.0
        elif h3_count >= 1:
            score += 8.0

        # Lists
        list_count = ul_count + ol_count
        if list_count >= 3:
            score += 25.0
        elif list_count >= 1:
            score += 12.0

        # Tables and blockquotes add signal richness
        if table_count >= 1:
            score += 15.0
        if blockquote_count >= 1:
            score += 10.0

        # Bonus: good paragraph density in text
        paragraphs = [p for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
        if len(paragraphs) >= 5:
            score += 5.0

    else:
        # Fallback: analyse text structure with regex
        lines = text.splitlines()
        short_lines = sum(1 for l in lines if 10 < len(l.strip()) < 80)
        if short_lines >= 5:
            score += 20.0
        bullet_like = len(re.findall(r"^\s*[-*•]\s+", text, re.MULTILINE))
        if bullet_like >= 3:
            score += 20.0

    return min(100.0, score)


def _score_schema_presence(html: Optional[str]) -> float:
    """
    Schema Presence Score — 10%.

    Structured data (JSON-LD, FAQ schema, Article schema, Open Graph)
    directly signals page intent and topic to AI crawlers. Pages with
    rich schema are significantly more likely to be cited.

    Parameters
    ----------
    html : Optional[str]
        Raw HTML.

    Returns
    -------
    float
        Score 0–100.
    """
    if not html:
        return 0.0

    score = 0.0
    html_lower = html.lower()

    # JSON-LD block present
    if "application/ld+json" in html_lower:
        score += 40.0
        # Bonus for specific high-value schema types
        for schema_type in ("faqpage", "article", "howto", "breadcrumb", "product", "review"):
            if schema_type in html_lower:
                score += 10.0

    # Open Graph tags
    og_count = len(re.findall(r'property=["\']og:', html_lower))
    if og_count >= 4:
        score += 20.0
    elif og_count >= 1:
        score += 10.0

    # Twitter card
    if 'name=["\']twitter:' in html_lower or "twitter:card" in html_lower:
        score += 10.0

    # Meta description
    if re.search(r'name=["\']description["\']', html_lower):
        score += 5.0

    # Canonical tag
    if "rel=\"canonical\"" in html_lower or "rel='canonical'" in html_lower:
        score += 5.0

    return min(100.0, score)


def _score_claim_support(text: str, html: Optional[str]) -> float:
    """
    Claim Support Score — 12%.

    Measures how well the page's factual claims are supported by
    proximate citations or references. AI systems look for evidence
    that assertions are grounded, not asserted without backup.

    Detects:
    - Inline numeric citations [1], [2], (Smith 2023), (Source: X)
    - Outbound links near claim sentences (sentences with numbers/stats)
    - Explicit attribution phrases ("according to", "research by", etc.)

    Parameters
    ----------
    text : str
        Cleaned page text.
    html : Optional[str]
        Raw HTML for link proximity checks.

    Returns
    -------
    float
        Score 0–100.
    """
    if not text:
        return 0.0

    score = 0.0

    # Inline citation patterns: [1], [12], (1), (Smith, 2023)
    inline_citations = re.findall(
        r"\[\d{1,3}\]"              # [1], [23]
        r"|\(\d{1,3}\)"             # (1)
        r"|\([A-Z][a-z]+,?\s+\d{4}\)"  # (Author, 2023)
        r"|\(Source:[^)]{3,40}\)",  # (Source: Reuters)
        text
    )
    score += min(30.0, len(inline_citations) * 5.0)

    # Attribution phrases
    attribution_phrases = re.findall(
        r"\baccording to\b|\bstudy by\b|\bresearch by\b|\breported by\b"
        r"|\bcited by\b|\bsource:\b|\breferences?\b|\bbased on\b"
        r"|\bdata from\b|\bpublished (?:in|by)\b",
        text, re.IGNORECASE
    )
    score += min(25.0, len(attribution_phrases) * 5.0)

    # Factual sentences (contain numbers) — check if outbound links are nearby
    if html:
        soup = BeautifulSoup(html, "html.parser")
        paragraphs = soup.find_all("p")
        linked_claim_count = 0
        for p in paragraphs:
            p_text = p.get_text()
            has_number = bool(re.search(r"\d", p_text))
            has_link = bool(p.find("a", href=True))
            if has_number and has_link:
                linked_claim_count += 1
        score += min(30.0, linked_claim_count * 6.0)

    # Penalise pages with many numeric claims but zero citation signals
    numeric_claims = len(re.findall(r"\b\d+(?:\.\d+)?%|\b\d{4}\b|\$\d+", text))
    if numeric_claims > 5 and len(inline_citations) == 0 and len(attribution_phrases) == 0:
        score = max(0.0, score - 15.0)

    return min(100.0, score)


def _score_readability(text: str) -> float:
    """
    Readability Score — 10%.

    Uses a heuristic approximation of reading ease based on average
    sentence length and average word length. Short, clear sentences
    with common vocabulary score highest — the style that AI systems
    can most easily parse and cite.

    No external libraries. Pure regex and arithmetic.

    Approximate Flesch mapping (no syllable counting):
    - avg sentence length < 15 words AND avg word length < 5.5 chars → high
    - avg sentence length 15–22 words → medium
    - avg sentence length > 22 words → low

    Parameters
    ----------
    text : str
        Cleaned page text.

    Returns
    -------
    float
        Score 0–100.
    """
    if not text or len(text.strip()) < 50:
        return 0.0

    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    if not sentences:
        return 40.0

    word_counts = [len(s.split()) for s in sentences]
    avg_sentence_length = sum(word_counts) / len(word_counts)

    all_words = text.split()
    avg_word_length = (
        sum(len(re.sub(r"[^a-zA-Z]", "", w)) for w in all_words) / max(len(all_words), 1)
    )

    # Score sentence length (lower = better)
    if avg_sentence_length <= 12:
        sent_score = 100.0
    elif avg_sentence_length <= 18:
        sent_score = 100.0 - ((avg_sentence_length - 12) / 6.0) * 30.0
    elif avg_sentence_length <= 25:
        sent_score = 70.0 - ((avg_sentence_length - 18) / 7.0) * 30.0
    else:
        sent_score = max(10.0, 40.0 - (avg_sentence_length - 25) * 1.5)

    # Score word length (lower = better; penalise heavy jargon)
    if avg_word_length <= 4.5:
        word_score = 100.0
    elif avg_word_length <= 6.0:
        word_score = 100.0 - ((avg_word_length - 4.5) / 1.5) * 40.0
    else:
        word_score = max(20.0, 60.0 - (avg_word_length - 6.0) * 10.0)

    # Blend 70/30 sentence vs word length
    return round(sent_score * 0.70 + word_score * 0.30, 2)


# ===========================================================================
# Explainability text — static per metric
# ===========================================================================

_EXPLAINABILITY: Dict[str, Dict[str, str]] = {
    "BLUF Score": {
        "why_it_matters": (
            "AI systems scan pages to find the best answer to a query. Pages that "
            "state their answer immediately are far more likely to be quoted because "
            "the AI does not have to guess what the page is about."
        ),
        "how_ai_reads_it": (
            "Language models weight the opening sentences heavily when deciding whether "
            "a page answers a query. If the core answer is buried after three paragraphs "
            "of background, the model may move on to a competitor that answers first."
        ),
        "what_to_fix": (
            "Rewrite your first paragraph to directly state what this page covers and "
            "the single most important answer it provides. Lead with the conclusion, "
            "then support it with detail below."
        ),
    },
    "Entity Density": {
        "why_it_matters": (
            "AI systems treat named entities — people, organisations, places, dates, "
            "and specific data points — as credibility signals. Generic text with no "
            "concrete references reads as opinion, not fact."
        ),
        "how_ai_reads_it": (
            "Language models are trained to associate entities with factual claims. "
            "A page rich in specific names, numbers, and dates is weighted as more "
            "authoritative than one that uses only vague, general language."
        ),
        "what_to_fix": (
            "Add real names, specific organisations, verified data points, and dated "
            "statistics. Replace phrases like 'many experts agree' with 'Dr. Jane Smith "
            "of Harvard Medical School (2023) found that...'"
        ),
    },
    "Link Authority": {
        "why_it_matters": (
            "Outbound links to credible sources show AI systems that your claims are "
            "grounded in established knowledge. A page with no external citations is "
            "harder to verify and therefore less likely to be cited itself."
        ),
        "how_ai_reads_it": (
            "AI search systems treat outbound links as a trust signal — the same way "
            "academic papers cite prior work. Linking to .gov, .edu, or major news "
            "organisations transfers credibility to your own content."
        ),
        "what_to_fix": (
            "Add at least 3 to 5 outbound links to authoritative sources that back up "
            "your key claims. Prioritise government data, peer-reviewed research, and "
            "established news organisations over generic blog posts."
        ),
    },
    "Formatting Readiness": {
        "why_it_matters": (
            "AI systems parse structured content far more reliably than undivided "
            "blocks of text. Clear headings, bullet lists, and tables make it easy "
            "for a model to extract discrete facts and quote them accurately."
        ),
        "how_ai_reads_it": (
            "Language models use heading hierarchy to infer topic structure. A page "
            "with clear H2 and H3 sections looks like a well-organised reference "
            "document. A wall of prose looks like an essay — harder to cite precisely."
        ),
        "what_to_fix": (
            "Break your content into named sections using H2 and H3 headings. Convert "
            "any run-on lists in prose into proper bullet or numbered lists. Add a "
            "summary or FAQ section at the end to reinforce citable answers."
        ),
    },
    "Schema Presence": {
        "why_it_matters": (
            "Structured data (JSON-LD, FAQ schema, Article schema) is a direct signal "
            "to AI crawlers about what your page covers and how to categorise it. "
            "Pages with schema are indexed and understood faster and more accurately."
        ),
        "how_ai_reads_it": (
            "AI search systems prioritise pages where the machine-readable metadata "
            "confirms the topic and content type. FAQ schema in particular maps "
            "directly to question-and-answer retrieval patterns used by AI assistants."
        ),
        "what_to_fix": (
            "Add JSON-LD structured data to your page. At minimum, implement Article "
            "or BlogPosting schema with a headline, author, and datePublished. If your "
            "page answers common questions, add FAQPage schema for each Q&A pair."
        ),
    },
    "Claim Support": {
        "why_it_matters": (
            "AI systems are designed to avoid amplifying unsupported claims. Pages "
            "that back every assertion with a source, data reference, or outbound "
            "link are trusted more and cited more frequently as a result."
        ),
        "how_ai_reads_it": (
            "Language models look for proximity between a factual statement and its "
            "evidence. A statistic with a linked source directly below it scores "
            "significantly higher than the same statistic stated without any reference."
        ),
        "what_to_fix": (
            "For every significant claim or statistic on the page, add an inline "
            "citation or a linked source immediately after it. Use phrases like "
            "'according to [Source]' or '(data: Organisation, 2024)' to make the "
            "attribution explicit and machine-readable."
        ),
    },
    "Readability": {
        "why_it_matters": (
            "AI systems retrieve and paraphrase content. Pages written in clear, "
            "concise sentences are far easier to quote accurately than dense, "
            "jargon-heavy text that requires interpretation."
        ),
        "how_ai_reads_it": (
            "Shorter sentences and common vocabulary reduce parsing ambiguity. When "
            "a language model must simplify complex sentences to use them in a "
            "response, meaning is often lost — so simpler source text wins."
        ),
        "what_to_fix": (
            "Aim for an average sentence length below 18 words. Split long sentences "
            "at conjunctions or semi-colons. Replace technical jargon with plain "
            "equivalents wherever the audience allows it. Read each paragraph aloud "
            "— if you run out of breath, the sentence is too long."
        ),
    },
    "Search Presence": {
        "why_it_matters": (
            "If your page is not visible in organic search results, AI systems trained "
            "on web crawl data are far less likely to have indexed it at all. "
            "Search visibility is the foundation that all other signals depend on."
        ),
        "how_ai_reads_it": (
            "AI systems source their knowledge primarily from content that ranks in "
            "search. A page that does not appear in results for its own topic has "
            "little chance of being included in AI training data or cited in responses."
        ),
        "what_to_fix": (
            "Ensure your page targets a clear, specific keyword. Build internal links "
            "from other pages on your site to this page. Acquire at least a few "
            "backlinks from relevant, credible external sources. Submit your sitemap "
            "to Google Search Console and verify indexation."
        ),
    },
}


# ===========================================================================
# Main public function
# ===========================================================================


def compute_cqs(
    page_config: PageConfig,
    page_data: dict,
    search_presence: float,
) -> Tuple[List[MetricScore], float, dict]:
    """
    Compute the Citation Quality Score (CQS) for a single page.

    Orchestrates all 8 metric scorers, applies page status penalties,
    assembles MetricScore objects with full explainability, and returns
    the final weighted CQS.

    Parameters
    ----------
    page_config : PageConfig
        Input configuration (URL, optional keyword, optional brand name).
    page_data : dict
        Output dict from fetcher.fetch_page(). Expected keys:
        status, url, html, text, title, word_count.
    search_presence : float
        Pre-computed search presence score (0–100) from SearchPresence.score.

    Returns
    -------
    Tuple[List[MetricScore], float, dict]
        - List of 8 MetricScore objects (with explainability)
        - Final CQS as a float rounded to 2 decimal places (0–100)
        - Debug dict (raw scores before penalty, for internal diagnostics)
    """
    status = page_data.get("status", "failed")
    html = page_data.get("html")
    text = page_data.get("text") or ""
    title = page_data.get("title") or ""
    keyword = page_config.target_keyword

    # --- Raw metric scores ---
    if status == "failed":
        raw_scores = {name: 0.0 for name in WEIGHTS}
    else:
        raw_scores = {
            "BLUF Score":           _score_bluf(text, keyword, title),
            "Entity Density":       _score_entity_density(text),
            "Link Authority":       _score_link_authority(html),
            "Formatting Readiness": _score_formatting_readiness(html, text),
            "Schema Presence":      _score_schema_presence(html),
            "Claim Support":        _score_claim_support(text, html),
            "Readability":          _score_readability(text),
            "Search Presence":      float(max(0.0, min(100.0, search_presence))),
        }

    debug = {"raw_scores_before_penalty": dict(raw_scores), "status": status}

    # --- Limited access penalty: reduce all metrics by 40% ---
    if status == "limited_access":
        raw_scores = {k: v * _LIMITED_ACCESS_MULTIPLIER for k, v in raw_scores.items()}

    # --- Clamp all scores to 0–100 ---
    raw_scores = {k: max(0.0, min(100.0, v)) for k, v in raw_scores.items()}

    # --- Assemble MetricScore objects ---
    metric_scores: List[MetricScore] = []
    cqs_accumulator = 0.0

    for name, weight in WEIGHTS.items():
        score = raw_scores[name]
        weighted = round(score * weight, 4)
        cqs_accumulator += weighted

        explainability = _EXPLAINABILITY[name]
        metric_scores.append(
            MetricScore(
                name=name,
                score=round(score, 2),
                weight=weight,
                weighted_score=weighted,
                why_it_matters=explainability["why_it_matters"],
                how_ai_reads_it=explainability["how_ai_reads_it"],
                what_to_fix=explainability["what_to_fix"],
            )
        )

    final_cqs = round(max(0.0, min(100.0, cqs_accumulator)), 2)
    debug["final_cqs"] = final_cqs

    return metric_scores, final_cqs, debug


