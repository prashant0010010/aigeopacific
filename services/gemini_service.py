"""
services/gemini_service.py
==========================
Google Gemini LLM enrichment layer for the AiGeoPacific AI Citation Analyser.

Responsibilities:
- Send a single structured request to Gemini 1.5 Flash per audit
- Parse and validate the JSON response into an EnrichmentResult Pydantic model
- Fall back to heuristic_service.generate_enrichment() on any failure

This module never crashes the pipeline. Every exception path returns a valid
EnrichmentResult, either from Gemini or from the heuristic fallback.

Allowed imports: json, re, typing, google.generativeai, core.models,
                 services.heuristic_service.
"""

import json
import re
from typing import Optional

from core.models import EnrichmentResult
from services import heuristic_service

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GEMINI_MODEL: str = "gemini-1.5-flash"
_MAX_TEXT_CHARS: int = 30_000   # safe heuristic cap to stay within free-tier limits

_PROMPT_TEMPLATE: str = """
You are an expert SEO and AI citation analyst. You are analysing a webpage audit
for the AiGeoPacific Citation Analyzer tool.

Your task is to generate actionable insights that will help this page get cited
by AI systems like ChatGPT, Perplexity, and Google AI Overviews.

## Audit Data

URL: {url}

Citation Quality Score (CQS): {cqs}/100

Metric Scores:
{metric_scores}

Competitor Comparison:
{competitor_comparison}

Page Content Excerpt:
{text_excerpt}

## Instructions

Return ONLY a valid JSON object with exactly these keys. No preamble, no markdown,
no explanation — raw JSON only.

{{
  "business_impact": "A 2-3 sentence plain-English paragraph explaining the business
    cost of this page's current AI citation visibility. Be specific to the CQS score.",

  "quick_wins": [
    "Fastest, highest-leverage fix #1 (one sentence)",
    "Fastest, highest-leverage fix #2 (one sentence)",
    "Fastest, highest-leverage fix #3 (one sentence)"
  ],

  "recommendations": [
    {{"priority": "🔥", "action": "Highest impact action, specific and actionable"}},
    {{"priority": "🔥", "action": "Second high impact action"}},
    {{"priority": "⚙️", "action": "Medium effort improvement"}},
    {{"priority": "⚙️", "action": "Another medium effort improvement"}},
    {{"priority": "🚀", "action": "Long-term strategic improvement"}}
  ],

  "ideal_targets": {{
    "word_count": <recommended minimum word count as integer>,
    "link_percentage": <recommended percentage of sentences with outbound links as float>,
    "cqs": <target CQS score to aim for as integer>
  }},

  "competitor_insight": "One paragraph explaining why competitor pages outperform
    this page in AI citation, based on the competitor comparison data.",

  "llm_key_signals": {{
    "chatgpt": "One sentence on what this CQS score means for ChatGPT citation likelihood.",
    "perplexity": "One sentence on what this CQS score means for Perplexity citation likelihood.",
    "claude": "One sentence on what this CQS score means for Claude citation likelihood."
  }},

  "suggested_search_prompts": [
    "Natural language query this page should aim to appear in #1",
    "Natural language query this page should aim to appear in #2",
    "Natural language query this page should aim to appear in #3",
    "Natural language query this page should aim to appear in #4",
    "Natural language query this page should aim to appear in #5",
    "Natural language query this page should aim to appear in #6"
  ]
}}
"""


# ===========================================================================
# Prompt construction
# ===========================================================================


def _build_prompt(audit_data: dict) -> str:
    """
    Build the structured Gemini prompt from audit data.

    Caps page text at _MAX_TEXT_CHARS to stay within free-tier token limits.
    Formats metric scores and competitor data as readable strings.

    Parameters
    ----------
    audit_data : dict
        Expected keys: url, text, cqs, metric_scores, competitor_comparison.

    Returns
    -------
    str
        Fully formatted prompt string ready for Gemini.
    """
    url = audit_data.get("url", "Unknown URL")
    cqs = audit_data.get("cqs", 0)
    text = audit_data.get("text") or ""
    text_excerpt = text[:_MAX_TEXT_CHARS]

    # Format metric scores as a readable list
    raw_metrics = audit_data.get("metric_scores", [])
    if raw_metrics and isinstance(raw_metrics[0], dict):
        metric_lines = [
            f"  - {m.get('name', 'Unknown')}: {m.get('score', 0):.0f}/100"
            for m in raw_metrics
        ]
    else:
        # Handle MetricScore Pydantic objects
        try:
            metric_lines = [
                f"  - {m.name}: {m.score:.0f}/100"
                for m in raw_metrics
            ]
        except AttributeError:
            metric_lines = ["  - Metric data unavailable"]

    metric_scores_str = "\n".join(metric_lines) if metric_lines else "  - No metric data available"

    # Format competitor comparison
    raw_competitors = audit_data.get("competitor_comparison", {})
    if isinstance(raw_competitors, dict):
        comp_list = raw_competitors.get("competitors", [])
        gaps = raw_competitors.get("gaps", [])
    else:
        # Handle CompetitorComparison Pydantic object
        try:
            comp_list = [c.model_dump() for c in raw_competitors.competitors]
            gaps = raw_competitors.gaps
        except AttributeError:
            comp_list = []
            gaps = []

    comp_lines = []
    for c in comp_list:
        if isinstance(c, dict):
            comp_lines.append(f"  - {c.get('competitor_url', 'Unknown')} | CQS: {c.get('cqs', 0):.0f}")
        else:
            try:
                comp_lines.append(f"  - {c.competitor_url} | CQS: {c.cqs:.0f}")
            except AttributeError:
                pass

    if gaps:
        comp_lines.append("  Gaps identified:")
        for gap in gaps[:5]:
            comp_lines.append(f"    * {gap}")

    competitor_str = (
        "\n".join(comp_lines)
        if comp_lines
        else "  No competitor data available."
    )

    return _PROMPT_TEMPLATE.format(
        url=url,
        cqs=cqs,
        metric_scores=metric_scores_str,
        competitor_comparison=competitor_str,
        text_excerpt=text_excerpt,
    )


# ===========================================================================
# JSON extraction and parsing
# ===========================================================================


def _extract_json(response_text: str) -> Optional[dict]:
    """
    Safely extract and parse a JSON object from a Gemini response string.

    Handles common LLM formatting artifacts:
    - Markdown code fences (```json ... ```)
    - Leading/trailing whitespace
    - Embedded text before or after the JSON block

    Parameters
    ----------
    response_text : str
        Raw text returned by Gemini.

    Returns
    -------
    Optional[dict]
        Parsed dict on success, None on any parse failure.
    """
    if not response_text or not response_text.strip():
        return None

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", response_text)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    # Attempt direct parse first (response_mime_type=application/json should give clean output)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first {...} block using regex
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _parse_enrichment(parsed: dict) -> Optional[EnrichmentResult]:
    """
    Validate a parsed JSON dict into an EnrichmentResult Pydantic model.

    Normalises field types defensively before Pydantic validation so that
    minor schema deviations from Gemini do not trigger hard failures.

    Parameters
    ----------
    parsed : dict
        Raw parsed JSON from Gemini response.

    Returns
    -------
    Optional[EnrichmentResult]
        Populated model on success, None if validation fails.
    """
    try:
        # Normalise ideal_targets — Gemini may return string numbers
        ideal_targets_raw = parsed.get("ideal_targets", {})
        ideal_targets: dict = {}
        for k, v in ideal_targets_raw.items():
            try:
                ideal_targets[k] = float(v)
            except (TypeError, ValueError):
                ideal_targets[k] = 0.0

        # Normalise recommendations — ensure list of dicts with priority + action
        raw_recs = parsed.get("recommendations", [])
        recommendations = []
        for rec in raw_recs:
            if isinstance(rec, dict) and "action" in rec:
                recommendations.append({
                    "priority": str(rec.get("priority", "⚙️")),
                    "action": str(rec.get("action", "")),
                })

        # Normalise llm_key_signals — must be Dict[str, str]
        raw_signals = parsed.get("llm_key_signals", {})
        llm_key_signals = {
            str(k): str(v) for k, v in raw_signals.items()
        }

        # Normalise competitor_insight — may be string or list
        competitor_insight_raw = parsed.get("competitor_insight", "")
        if isinstance(competitor_insight_raw, list):
            competitor_insight = [str(c) for c in competitor_insight_raw]
        elif isinstance(competitor_insight_raw, str):
            competitor_insight = [competitor_insight_raw] if competitor_insight_raw else []
        else:
            competitor_insight = []

        # Normalise string list fields
        def _to_str_list(val, default=None):
            if isinstance(val, list):
                return [str(item) for item in val if item]
            return default or []

        return EnrichmentResult(
            business_impact=str(parsed.get("business_impact", "")),
            quick_wins=_to_str_list(parsed.get("quick_wins")),
            recommendations=recommendations,
            ideal_targets=ideal_targets,
            competitor_insight=competitor_insight,
            llm_key_signals=llm_key_signals,
            suggested_search_prompts=_to_str_list(parsed.get("suggested_search_prompts")),
        )

    except Exception as exc:
        print(f"[Gemini] EnrichmentResult validation failed: {exc}")
        return None


# ===========================================================================
# Main public function
# ===========================================================================


def generate_enrichment(
    audit_data: dict,
    api_key: Optional[str] = None,
) -> EnrichmentResult:
    """
    Generate AI-enriched narrative for a page audit using Google Gemini.

    Sends a single structured request to Gemini 1.5 Flash and parses the
    JSON response into an EnrichmentResult Pydantic model.

    Falls back to heuristic_service.generate_enrichment() if:
    - No API key is provided
    - The Gemini API call fails (network error, rate limit, etc.)
    - The response cannot be parsed as valid JSON
    - The parsed JSON cannot be validated into EnrichmentResult

    This function never raises — it always returns a valid EnrichmentResult.

    Parameters
    ----------
    audit_data : dict
        Audit payload with keys: url, text, cqs, metric_scores,
        competitor_comparison.
    api_key : Optional[str]
        Google Gemini API key. If None or empty, falls back to heuristic.

    Returns
    -------
    EnrichmentResult
        Populated enrichment model from Gemini or heuristic fallback.
    """
    # --- Guard: no API key → skip Gemini entirely ---
    if not api_key or not api_key.strip():
        print("[Gemini] No API key provided — using heuristic fallback.")
        return heuristic_service.generate_enrichment(audit_data)

    # --- Configure Gemini client ---
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key.strip())
        model = genai.GenerativeModel(
            model_name=_GEMINI_MODEL,
            generation_config={"response_mime_type": "application/json"},
        )
    except Exception as exc:
        print(f"[Gemini] Configuration failed: {exc}")
        return heuristic_service.generate_enrichment(audit_data)

    # --- Build prompt ---
    try:
        prompt = _build_prompt(audit_data)
    except Exception as exc:
        print(f"[Gemini] Prompt construction failed: {exc}")
        return heuristic_service.generate_enrichment(audit_data)

    # --- Call Gemini API ---
    try:
        print("[Gemini] Sending enrichment request to Gemini 1.5 Flash...")
        response = model.generate_content(prompt)
        response_text = response.text
        print("[Gemini] Response received.")
    except Exception as exc:
        print(f"[Gemini] API call failed: {exc}")
        return heuristic_service.generate_enrichment(audit_data)

    # --- Parse JSON response ---
    try:
        parsed = _extract_json(response_text)
        if parsed is None:
            print("[Gemini] JSON extraction returned None — using heuristic fallback.")
            return heuristic_service.generate_enrichment(audit_data)
    except Exception as exc:
        print(f"[Gemini] JSON extraction error: {exc}")
        return heuristic_service.generate_enrichment(audit_data)

    # --- Validate into Pydantic model ---
    enrichment = _parse_enrichment(parsed)
    if enrichment is None:
        print("[Gemini] Pydantic validation failed — using heuristic fallback.")
        return heuristic_service.generate_enrichment(audit_data)

    print("[Gemini] Enrichment generated successfully.")
    return enrichment