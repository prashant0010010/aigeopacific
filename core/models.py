"""
core/models.py
==============
Pydantic data models for the AiGeoPacific AI Citation Analyser.

This module defines the complete data contract for the system. Every module
(scorer, competitor, PDF builder, UI) consumes and produces these models.
No business logic lives here — only structure, types, and validation.

Phase 2 additions:
- PageConfig:  keyword_prompts, gemini_api_key, perplexity_api_key fields
- AuditResult: timestamp, confidence_level, prompt_presence, citation_check, delta fields
- AuditMeta:           NEW — lightweight audit history metadata for sidebar panel
- PromptPresenceResult: NEW — per-prompt keyword visibility result
- CitationEvent:       NEW — single AI citation detection event
- CitationCheckResult: NEW — full citation detection run output
- AuditDelta:          NEW — score comparison between two AuditResult objects
"""

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ===========================================================================
# Input models
# ===========================================================================


class PageConfig(BaseModel):
    """
    Input configuration for a single page audit.

    Phase 2: adds keyword_prompts (for prompt visibility testing and citation
    detection), gemini_api_key, and perplexity_api_key so that optional API
    keys can flow through the pipeline cleanly without relying on os.environ
    side-effects.
    """

    url: str = Field(..., description="Full URL of the page to audit.")
    target_keyword: Optional[str] = Field(
        default=None,
        description="Primary keyword or query this page should rank/answer for.",
    )
    brand_name: Optional[str] = Field(
        default=None,
        description="Brand or site name used for search presence matching.",
    )

    # Phase 2 additions
    keyword_prompts: List[str] = Field(
        default_factory=list,
        description=(
            "Up to 5 natural-language queries the user wants to test for AI visibility. "
            "Passed to search_service.check_prompt_presence() and citation_service.check_citations()."
        ),
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Google Gemini API key for AI enrichment. Heuristic fallback if None.",
    )
    perplexity_api_key: Optional[str] = Field(
        default=None,
        description="Perplexity API key for citation detection. DuckDuckGo AI fallback if None.",
    )


# ===========================================================================
# Metric models
# ===========================================================================


class MetricScore(BaseModel):
    """
    Score and explainability output for a single GEO metric.

    Each metric carries not just its numeric score but the full
    explainability layer required for the PDF report: why the signal
    matters, how LLMs interpret it, and what to fix if the score is low.
    """

    name: str = Field(..., description="Human-readable metric name (e.g. 'BLUF Score').")
    score: float = Field(..., ge=0.0, le=100.0, description="Raw metric score from 0 to 100.")
    weight: float = Field(..., gt=0.0, le=1.0, description="Weight of this metric in the CQS calculation.")
    weighted_score: float = Field(
        ..., description="score * weight. Pre-computed and stored for transparency."
    )
    why_it_matters: str = Field(
        ..., description="Why AI citation systems care about this signal."
    )
    how_ai_reads_it: str = Field(
        ..., description="How LLMs and AI search engines interpret this specific signal."
    )
    what_to_fix: str = Field(
        ..., description="Concrete, actionable fix if this score is low."
    )


# ===========================================================================
# Search / presence models
# ===========================================================================


class SearchPresence(BaseModel):
    """
    Reality validation result from DuckDuckGo search.

    Determines whether the audited URL or its brand is currently visible
    in organic search results.
    """

    status: Literal["exact_match", "brand_visible", "not_visible"] = Field(
        ...,
        description=(
            "exact_match: audited URL found in top results. "
            "brand_visible: brand/title found but not the exact URL. "
            "not_visible: neither found."
        ),
    )
    score: float = Field(
        ..., ge=0.0, le=100.0, description="Numeric score for this dimension (0-100)."
    )
    found_url: Optional[str] = Field(
        default=None, description="The matching URL found in search results, if any."
    )
    matched_text: Optional[str] = Field(
        default=None,
        description="Snippet or title text that triggered a brand/title match, if any.",
    )


# ===========================================================================
# Phase 2 — Prompt presence
# ===========================================================================


class PromptPresenceResult(BaseModel):
    """
    Result of testing a single keyword prompt for page/domain visibility.

    Produced by search_service.check_prompt_presence() for each entry in
    PageConfig.keyword_prompts. Stored in AuditResult.prompt_presence.
    """

    prompt: str = Field(..., description="The natural-language query that was tested.")
    visibility: Literal["exact_match", "brand_visible", "not_visible"] = Field(
        ...,
        description=(
            "exact_match: audited URL appears in results for this prompt. "
            "brand_visible: domain appears but not the exact URL. "
            "not_visible: neither URL nor domain found."
        ),
    )
    competitor_url: Optional[str] = Field(
        default=None,
        description="The top-ranking URL for this prompt when the user's page is not found.",
    )
    search_position: Optional[int] = Field(
        default=None,
        description="1-based position in search results where the URL/domain was matched.",
    )


# ===========================================================================
# Phase 2 — Citation detection
# ===========================================================================


class CitationEvent(BaseModel):
    """
    A single AI citation detection event.

    Produced when an AI system (Perplexity or DuckDuckGo AI) cites the
    target URL or domain in response to a tested prompt.
    """

    prompt: str = Field(..., description="The keyword prompt that triggered the citation.")
    cited_url: str = Field(..., description="The exact URL cited by the AI system.")
    citation_level: Literal["page", "domain"] = Field(
        ...,
        description=(
            "page: the exact audited URL was cited. "
            "domain: a different page on the same domain was cited."
        ),
    )
    context_snippet: str = Field(
        ...,
        description=(
            "Surrounding text from the AI response near the citation. "
            "Max 200 characters. Used as evidence in the report."
        ),
    )


class CitationCheckResult(BaseModel):
    """
    Full output of a citation detection run across all tested prompts.

    CRITICAL DISPLAY RULE (enforced by results_view.py and pdf_builder.py):
    - If citations_found is EMPTY: do NOT render a citation section anywhere.
    - Do NOT show a 'no citations found' banner.
    - Only render when citations_found is non-empty.
    """

    citations_found: List[CitationEvent] = Field(
        default_factory=list,
        description="All citation events detected. Empty list = no citations found.",
    )
    checked_prompts: int = Field(
        ..., description="Number of prompts that were actually checked."
    )
    method_used: Literal["perplexity", "duckduckgo_ai", "unavailable"] = Field(
        ...,
        description=(
            "perplexity: Perplexity API was used. "
            "duckduckgo_ai: DuckDuckGo AI Chat fallback was used. "
            "unavailable: neither method succeeded."
        ),
    )
    confidence_note: str = Field(
        ...,
        description=(
            "Displayed on every citation result. Example: "
            "'Sampled at time of audit. Results vary by AI session.'"
        ),
    )


# ===========================================================================
# Competitor models
# ===========================================================================


class CompetitorMetric(BaseModel):
    """
    Metric scores for a single competitor URL.
    """

    competitor_url: str = Field(..., description="Full URL of the competitor page.")
    metrics: Dict[str, float] = Field(
        ...,
        description="Map of metric name to raw score (0-100).",
    )
    cqs: float = Field(
        ..., ge=0.0, le=100.0, description="Competitor's overall Citation Quality Score."
    )


class CompetitorComparison(BaseModel):
    """
    Full competitor comparison result.
    """

    competitors: List[CompetitorMetric] = Field(
        default_factory=list,
        description="List of up to 3 scored competitor pages.",
    )
    gaps: List[str] = Field(
        default_factory=list,
        description="Plain-English explanations of why competitors outperform the user's page.",
    )


# ===========================================================================
# Confidence model
# ===========================================================================


class ConfidenceResult(BaseModel):
    """
    Confidence level for the overall audit result.
    """

    level: Literal["High", "Medium", "Low"] = Field(
        ...,
        description=(
            "High: search data available + content >1000 words + 6+ signals. "
            "Medium: partial search data OR 300-999 words OR 3-5 signals. "
            "Low: no search data OR <300 words OR <3 signals."
        ),
    )
    reasoning: str = Field(
        ...,
        description="Human-readable explanation of why this confidence level was assigned.",
    )


# ===========================================================================
# Enrichment model
# ===========================================================================


class EnrichmentResult(BaseModel):
    """
    AI-enriched or heuristic-generated narrative layer.

    Produced either by a single Gemini API batch call (when a key is
    provided) or by heuristic_service.py (fallback). Structure is
    identical in both cases.
    """

    business_impact: str = Field(
        ...,
        description="Plain-English paragraph explaining the business cost of low AI citation visibility.",
    )
    quick_wins: List[str] = Field(
        default_factory=list,
        description="3 to 5 fastest, highest-leverage fixes the user can make.",
    )
    recommendations: List[Dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Prioritised list of actions. Each dict has keys: "
            "'priority' (tier label) and 'action' (specific step)."
        ),
    )
    ideal_targets: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Numeric targets to aim for. Expected keys: "
            "target_cqs, recommended_word_count, external_link_percentage, minimum_sources."
        ),
    )
    competitor_insight: List[str] = Field(
        default_factory=list,
        description="One entry per competitor explaining why it outperforms the user's page.",
    )
    llm_key_signals: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-LLM signal summary. Keys: model names. Values: one-sentence summaries.",
    )
    suggested_search_prompts: List[str] = Field(
        default_factory=list,
        description="6 natural-language search queries the page should aim to appear in.",
    )


# ===========================================================================
# Phase 2 — Delta model
# ===========================================================================


class AuditDelta(BaseModel):
    """
    Score comparison between two AuditResult objects for the same URL.

    Computed by core/delta.py when a previous audit exists for the
    same URL. Stored in AuditResult.delta and used by:
    - ui/results_view.py: _render_delta_section()
    - ui/history_view.py: _render_delta_section()
    - reports/pdf_builder.py: _draw_delta_section()
    """

    url: str = Field(..., description="The audited URL both results belong to.")
    audit_a_timestamp: datetime = Field(..., description="Timestamp of the older audit.")
    audit_b_timestamp: datetime = Field(..., description="Timestamp of the newer audit.")
    cqs_delta: float = Field(
        ...,
        description="CQS change: newer_cqs - older_cqs. Positive = improvement.",
    )
    metric_deltas: Dict[str, float] = Field(
        default_factory=dict,
        description="Per-metric delta: metric_name -> (newer_score - older_score).",
    )
    improved_metrics: List[str] = Field(
        default_factory=list,
        description="Metric names where score increased by more than 1 point.",
    )
    regressed_metrics: List[str] = Field(
        default_factory=list,
        description="Metric names where score decreased by more than 1 point.",
    )
    unchanged_metrics: List[str] = Field(
        default_factory=list,
        description="Metric names within the +/-1 point unchanged threshold.",
    )
    summary: str = Field(
        ...,
        description="Plain-English summary. Example: 'CQS improved from 43 to 61 (+18 points)'",
    )


# ===========================================================================
# Phase 2 — Audit metadata (for history sidebar)
# ===========================================================================


class AuditMeta(BaseModel):
    """
    Lightweight metadata for a saved audit.

    Stored in and read from ~/.aigeopacific/audits/*.json by core/storage.py.
    Used by ui/history_view.py to populate the sidebar history panel
    without loading full AuditResult objects.
    """

    url: str = Field(..., description="The audited page URL.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the audit was run.",
    )
    cqs: float = Field(..., ge=0.0, le=100.0, description="Citation Quality Score.")
    confidence_level: str = Field(
        default="Low",
        description="High / Medium / Low — matches ConfidenceResult.level.",
    )
    file_path: str = Field(..., description="Absolute path to the saved JSON audit file.")


# ===========================================================================
# Top-level audit result
# ===========================================================================


class AuditResult(BaseModel):
    """
    Top-level output container for a completed page audit.

    Phase 2 additions:
    - timestamp:        when the audit was run (used by storage and delta)
    - confidence_level: top-level shortcut to confidence.level (used by AuditMeta)
    - prompt_presence:  per-prompt keyword visibility results
    - citation_check:   full citation detection run output (None if not run)
    - delta:            score comparison against previous audit (None if first run)

    status reflects the quality of the fetch and scoring run:
    - success: full data, all metrics scored
    - partial:  some URLs failed or content was limited
    - failed:   page could not be fetched or scored at all
    """

    url: str = Field(..., description="The audited page URL.")
    cqs: float = Field(
        ..., ge=0.0, le=100.0, description="Citation Quality Score: weighted sum of all 8 metric scores."
    )
    metrics: List[MetricScore] = Field(
        default_factory=list,
        description="Scored results for all 8 Phase 1 metrics.",
    )
    search_presence: SearchPresence = Field(
        ..., description="Reality validation result from DuckDuckGo search."
    )
    competitor_comparison: CompetitorComparison = Field(
        ..., description="Side-by-side competitor scoring and gap analysis."
    )
    confidence: ConfidenceResult = Field(
        ..., description="Confidence level for this audit result."
    )
    enrichment: EnrichmentResult = Field(
        ..., description="AI or heuristic narrative enrichment layer."
    )
    status: Literal["success", "partial", "failed"] = Field(
        ..., description="Technical status of the audit pipeline."
    )
    status_message: str = Field(
        default="Pending",
        description="Human-readable status (e.g. 'Full page access').",
    )
    audit_summary: str = Field(
        default="",
        description="Short human-readable summary of the audit findings.",
    )

    # Phase 2 additions
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the audit was completed.",
    )
    confidence_level: str = Field(
        default="Low",
        description=(
            "Top-level shortcut to confidence.level. "
            "Set by audit_runner.py after confidence is calculated. "
            "Used by AuditMeta without needing to unwrap the nested object."
        ),
    )
    prompt_presence: List[PromptPresenceResult] = Field(
        default_factory=list,
        description=(
            "Visibility results for each keyword prompt tested. "
            "Empty list if no keyword_prompts were provided in PageConfig."
        ),
    )
    citation_check: Optional[CitationCheckResult] = Field(
        default=None,
        description=(
            "Full citation detection result. None if citation detection was not run "
            "(no prompts available or method unavailable)."
        ),
    )
    delta: Optional[AuditDelta] = Field(
        default=None,
        description=(
            "Score comparison against the previous audit of this URL. "
            "None if this is the first audit of this URL."
        ),
    )