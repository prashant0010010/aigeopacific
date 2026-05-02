"""
services/citation_service.py
-----------------------------
AI citation detection for AiGeoPacific.

Checks whether a target URL or domain is cited by AI systems when
answering the user's keyword prompts. This is Phase 2's most strategically
important feature — it provides real evidence of AI visibility, not
just a heuristic prediction.

Detection strategy (in priority order):
  1. Perplexity API (sonar-small-online) — best quality, requires API key
  2. DuckDuckGo AI Chat — no API key, rate-limited, used as fallback
  3. Unavailable — returns CitationCheckResult with empty citations_found
     and method_used="unavailable". NEVER raises.

CRITICAL DISPLAY RULE (enforced by caller, documented here):
  - If citations_found is EMPTY: do NOT render this section anywhere.
    No "no citations found" banner. Absence is communicated by the CQS score.
  - If citations ARE found: show a dedicated "AI Citations Detected" section
    with a green banner and the citation events listed.
  - Always label results: "Citations detected during audit
    (results may vary by AI session)."

This module has zero Streamlit or PDF imports. Pure service logic only.

Imported by:
  - core/audit_runner.py: check_citations() called after scoring if prompts exist
"""

import json
import logging
import re
import time
from typing import Optional

import requests

from core.models import CitationCheckResult, CitationEvent

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
_PERPLEXITY_MODEL = "sonar-small-online"

# Max characters of AI response context to store per citation
_MAX_CONTEXT_SNIPPET = 200

# Seconds to wait between prompt checks (rate-limit courtesy)
_INTER_PROMPT_DELAY = 1.5

# Per-request timeout for Perplexity API calls
_REQUEST_TIMEOUT = 20

# Confidence note attached to every CitationCheckResult
_CONFIDENCE_NOTE = (
    "Sampled at time of audit. AI citation results vary by session, "
    "query phrasing, and model version."
)


# ------------------------------------------------------------------
# Internal: URL / domain matching helpers
# ------------------------------------------------------------------

def _normalise_domain(url: str) -> str:
    """
    Extract the bare domain from a URL for loose matching.

    Args:
        url: Full URL string.

    Returns:
        Lowercase domain without scheme or www.
        Example: "https://www.ahrefs.com/blog/" -> "ahrefs.com"
    """
    domain = url.lower().strip()
    domain = re.sub(r'^https?://', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    domain = domain.split('/')[0]
    return domain


def _normalise_url(url: str) -> str:
    """
    Normalise a URL for exact-match comparison.

    Strips scheme, www, and trailing slash. Lowercases.

    Args:
        url: Raw URL string.

    Returns:
        Normalised URL string.
    """
    normalised = url.lower().strip()
    normalised = re.sub(r'^https?://', '', normalised)
    normalised = re.sub(r'^www\.', '', normalised)
    return normalised.rstrip('/')


def _classify_citation(
    cited_url: str,
    target_url: str,
    target_domain: str,
) -> Optional[str]:
    """
    Determine whether a cited URL matches the target at page or domain level.

    Args:
        cited_url:     URL extracted from the AI response.
        target_url:    The audited URL (normalised by caller).
        target_domain: The audited domain (e.g. "ahrefs.com").

    Returns:
        "page"   — exact URL match (same path)
        "domain" — same domain, different page
        None     — no match
    """
    norm_cited = _normalise_url(cited_url)
    cited_domain = _normalise_domain(cited_url)

    if norm_cited == target_url:
        return "page"
    if cited_domain == target_domain:
        return "domain"
    return None


def _extract_context_snippet(text: str, cited_url: str) -> str:
    """
    Extract up to _MAX_CONTEXT_SNIPPET characters of surrounding text
    near a cited URL mention in the AI response.

    Falls back to the first _MAX_CONTEXT_SNIPPET characters of the
    response if the URL is not found verbatim (AI may paraphrase).

    Args:
        text:      Full AI response text.
        cited_url: The URL to search for in the text.

    Returns:
        Context snippet string, stripped of excess whitespace.
    """
    idx = text.find(cited_url)
    if idx == -1:
        # URL not found verbatim — use response opening
        snippet = text[:_MAX_CONTEXT_SNIPPET].strip()
    else:
        # Take text around the citation (50 chars before, rest after)
        start = max(0, idx - 50)
        end = min(len(text), idx + _MAX_CONTEXT_SNIPPET)
        snippet = text[start:end].strip()

    # Collapse whitespace
    snippet = re.sub(r'\s+', ' ', snippet)
    return snippet[:_MAX_CONTEXT_SNIPPET]


# ------------------------------------------------------------------
# Internal: URL extraction from AI responses
# ------------------------------------------------------------------

def _extract_urls_from_text(text: str) -> list[str]:
    """
    Extract all URLs mentioned in an AI response text.

    Captures http/https URLs. Does not require them to be in Markdown
    link syntax — plain URLs in prose are also captured.

    Args:
        text: Raw AI response string.

    Returns:
        List of unique URL strings found, preserving order of first appearance.
    """
    pattern = r'https?://[^\s\)\]\'"<>]+'
    found = re.findall(pattern, text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for url in found:
        # Strip trailing punctuation that may have been captured
        url = url.rstrip('.,;:!?)')
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


# ------------------------------------------------------------------
# Internal: Perplexity API
# ------------------------------------------------------------------

def _query_perplexity(
    prompt: str,
    api_key: str,
) -> Optional[str]:
    """
    Send a single prompt to Perplexity's sonar-small-online model
    and return the response text.

    Args:
        prompt:  The natural language search query.
        api_key: Perplexity API key.

    Returns:
        Response text string, or None on any failure (network, auth, parse).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": _PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Answer the user's question "
                    "concisely and cite your sources with full URLs."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_tokens": 512,
        "return_citations": True,
    }

    try:
        response = requests.post(
            _PERPLEXITY_API_URL,
            headers=headers,
            json=payload,
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        # Extract text from the first message choice
        choices = data.get("choices", [])
        if not choices:
            logger.warning("Perplexity returned no choices for prompt: %s", prompt[:60])
            return None

        content = choices[0].get("message", {}).get("content", "")

        # Also append any structured citations Perplexity returns separately
        citations = data.get("citations", [])
        if citations:
            citation_block = "\n".join(citations)
            content = f"{content}\n\nSOURCES:\n{citation_block}"

        return content if content.strip() else None

    except requests.exceptions.Timeout:
        logger.warning("Perplexity API timeout for prompt: %s", prompt[:60])
        return None
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        logger.warning("Perplexity API HTTP %s for prompt: %s", status, prompt[:60])
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as exc:
        logger.warning("Perplexity API error (%s): %s", type(exc).__name__, exc)
        return None


# ------------------------------------------------------------------
# Internal: DuckDuckGo AI Chat fallback
# ------------------------------------------------------------------

def _query_duckduckgo_ai(prompt: str) -> Optional[str]:
    """
    Query DuckDuckGo AI Chat as a no-API-key fallback for citation detection.

    DuckDuckGo AI Chat uses GPT-3.5 or Claude-3 Haiku depending on the
    session. It has no official API, so this uses the unofficial endpoint.
    It is rate-limited and may return 429 — callers should handle None gracefully.

    Args:
        prompt: The natural language query.

    Returns:
        Response text string, or None if unavailable / rate-limited.
    """
    # Step 1: Get a vqd token (required for DuckDuckGo AI Chat)
    try:
        status_response = requests.get(
            "https://duckduckgo.com/duckchat/v1/status",
            headers={"x-vqd-accept": "1"},
            timeout=10,
        )
        vqd_token = status_response.headers.get("x-vqd-4", "")
        if not vqd_token:
            logger.warning("DuckDuckGo AI Chat: could not obtain vqd token.")
            return None
    except requests.exceptions.RequestException as exc:
        logger.warning("DuckDuckGo AI Chat status check failed: %s", exc)
        return None

    # Step 2: Send the query
    try:
        chat_response = requests.post(
            "https://duckduckgo.com/duckchat/v1/chat",
            headers={
                "x-vqd-4": vqd_token,
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_REQUEST_TIMEOUT,
            stream=True,
        )

        if chat_response.status_code == 429:
            logger.warning("DuckDuckGo AI Chat: rate limited (429).")
            return None

        chat_response.raise_for_status()

        # DuckDuckGo streams SSE events — parse text chunks
        full_text = ""
        for line in chat_response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8") if isinstance(line, bytes) else line
            if decoded.startswith("data: "):
                chunk_str = decoded[6:]
                if chunk_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(chunk_str)
                    message_content = chunk.get("message", "")
                    if message_content:
                        full_text += message_content
                except (json.JSONDecodeError, KeyError):
                    continue

        return full_text.strip() if full_text.strip() else None

    except requests.exceptions.RequestException as exc:
        logger.warning("DuckDuckGo AI Chat query failed: %s", exc)
        return None


# ------------------------------------------------------------------
# Internal: Single-prompt citation check
# ------------------------------------------------------------------

def _check_single_prompt(
    prompt: str,
    target_url: str,
    target_domain: str,
    api_key: Optional[str],
) -> list[CitationEvent]:
    """
    Run one prompt through the available AI backend and return any
    CitationEvent objects found for the target URL/domain.

    Tries Perplexity first (if api_key provided), then DuckDuckGo AI.
    Returns an empty list if neither produces a usable response.

    Args:
        prompt:        The natural language query.
        target_url:    Normalised target URL.
        target_domain: Target domain (e.g. "ahrefs.com").
        api_key:       Optional Perplexity API key.

    Returns:
        List of CitationEvent objects (may be empty).
    """
    response_text: Optional[str] = None
    method_attempted = "unavailable"

    if api_key:
        response_text = _query_perplexity(prompt, api_key)
        method_attempted = "perplexity"

    if response_text is None:
        response_text = _query_duckduckgo_ai(prompt)
        method_attempted = "duckduckgo_ai"

    if not response_text:
        return []

    cited_urls = _extract_urls_from_text(response_text)
    events: list[CitationEvent] = []

    for cited_url in cited_urls:
        level = _classify_citation(cited_url, target_url, target_domain)
        if level is not None:
            snippet = _extract_context_snippet(response_text, cited_url)
            events.append(
                CitationEvent(
                    prompt=prompt,
                    cited_url=cited_url,
                    citation_level=level,
                    context_snippet=snippet,
                )
            )

    if events:
        logger.info(
            "Citations found via %s for prompt '%s': %d event(s)",
            method_attempted, prompt[:60], len(events)
        )

    return events


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def check_citations(
    prompts: list[str],
    target_url: str,
    target_domain: str,
    api_key: Optional[str] = None,
) -> CitationCheckResult:
    """
    Check whether AI systems cite the target URL when answering each prompt.

    Iterates through all prompts, querying the best available AI backend
    for each. Collects all CitationEvent objects found across all prompts.

    This function NEVER raises. On any failure it returns a CitationCheckResult
    with an empty citations_found list and method_used="unavailable".

    DISPLAY RULE FOR CALLERS:
      - Render the citation section ONLY if result.citations_found is non-empty.
      - Never show a "no citations found" banner.

    Args:
        prompts:       List of natural language queries (up to 5 in Phase 2).
                       Empty list returns immediately with method="unavailable".
        target_url:    The audited URL (full, will be normalised internally).
        target_domain: The domain being audited (e.g. "ahrefs.com").
        api_key:       Optional Perplexity API key. If None, falls back to
                       DuckDuckGo AI Chat.

    Returns:
        CitationCheckResult — always populated, never None, never raises.
    """
    # Guard: empty prompts
    if not prompts:
        return CitationCheckResult(
            citations_found=[],
            checked_prompts=0,
            method_used="unavailable",
            confidence_note=_CONFIDENCE_NOTE,
        )

    norm_target_url = _normalise_url(target_url)
    norm_target_domain = _normalise_domain(target_domain)

    all_events: list[CitationEvent] = []
    method_used = "unavailable"
    checked = 0

    try:
        for i, prompt in enumerate(prompts):
            prompt = prompt.strip()
            if not prompt:
                continue

            logger.info(
                "Citation check [%d/%d]: '%s'",
                i + 1, len(prompts), prompt[:80]
            )

            events = _check_single_prompt(
                prompt=prompt,
                target_url=norm_target_url,
                target_domain=norm_target_domain,
                api_key=api_key,
            )
            all_events.extend(events)
            checked += 1

            # Determine method used (take the first successful method seen)
            if method_used == "unavailable" and events:
                # Infer from what worked
                if api_key:
                    method_used = "perplexity"
                else:
                    method_used = "duckduckgo_ai"

            # Courtesy delay between prompts to avoid rate-limiting
            if i < len(prompts) - 1:
                time.sleep(_INTER_PROMPT_DELAY)

        # If we checked prompts but found no citations, report method as
        # whichever backend was attempted (not "unavailable")
        if method_used == "unavailable" and checked > 0:
            method_used = "perplexity" if api_key else "duckduckgo_ai"

    except Exception as exc:
        # Belt-and-suspenders: this function must never raise
        logger.warning(
            "Unexpected error in check_citations for %s: %s",
            target_url, exc
        )

    return CitationCheckResult(
        citations_found=all_events,
        checked_prompts=checked,
        method_used=method_used,
        confidence_note=_CONFIDENCE_NOTE,
    )