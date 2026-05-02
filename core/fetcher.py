"""
core/fetcher.py
===============
HTML fetcher for the AiGeoPacific AI Citation Analyser.

Responsibilities:
- Retrieve raw HTML from a live URL or a local mock file
- Detect JavaScript-gated / bot-protected pages and return limited_access
- Parse and clean visible page text using BeautifulSoup
- Return a plain dictionary — never a Pydantic model

This module is intentionally "dumb and fast": no scoring, no models,
no external APIs. It is the first stage in the audit pipeline and must
never crash the system regardless of what a target URL returns.

Allowed imports: requests, bs4, typing, standard library only.
Do NOT import Streamlit, Pydantic models, or any project modules.
"""

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUEST_TIMEOUT: int = 10  # seconds

_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Phrases that indicate the page requires JavaScript to render meaningful content
_JS_SIGNALS: tuple = (
    "enable javascript",
    "javascript required",
    "please enable javascript",
    "requires javascript",
    "javascript is disabled",
    "turn on javascript",
)

_MIN_CONTENT_LENGTH: int = 500  # characters — below this triggers limited_access

# Tags whose content is always stripped from visible text
_STRIP_TAGS: tuple = ("script", "style", "noscript", "head", "meta", "link")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_page(
    url: str,
    mock_mode: bool = False,
    mock_path: Optional[str] = None,
) -> dict:
    """
    Fetch and parse a webpage, returning a plain dictionary.

    This is the sole public entry point for this module. All callers
    (audit_runner, competitor scorer, tests) use only this function.

    Parameters
    ----------
    url : str
        The fully qualified URL to fetch (e.g. "https://example.com/page").
    mock_mode : bool
        When True, load HTML from a local file instead of making an HTTP
        request. Intended for offline testing and CI pipelines.
    mock_path : Optional[str]
        Path to a local HTML file. Required when mock_mode=True.

    Returns
    -------
    dict
        Always returns one of three shapes:
        - success:       status, url, html, text, title, word_count
        - limited_access: status, reason, url, html=None, text=None,
                          title=None, word_count=0
        - failed:        status, reason, url, html=None, text=None,
                          title=None, word_count=0
    """
    if mock_mode:
        return _handle_mock(url, mock_path)

    raw_html = _fetch_html(url)
    if raw_html is None:
        # _fetch_html returns None only when it catches an exception;
        # the reason string is embedded in the tuple variant — see below.
        # This branch is unreachable when _fetch_html returns a tuple.
        return _failed(url, "Unknown fetch error")

    # _fetch_html returns (html_str, None) on success or (None, reason) on error
    html_content, error_reason = raw_html

    if error_reason is not None:
        return _failed(url, error_reason)

    return _process_html(url, html_content)


# ---------------------------------------------------------------------------
# Mock handling
# ---------------------------------------------------------------------------


def _handle_mock(url: str, mock_path: Optional[str]) -> dict:
    """
    Load HTML from a local file and process it as if it were fetched live.

    Parameters
    ----------
    url : str
        The URL string to associate with this result (used for reporting).
    mock_path : Optional[str]
        Filesystem path to a local .html file.

    Returns
    -------
    dict
        Processed result dict, or failed dict if mock_path is missing/unreadable.
    """
    if not mock_path:
        return _failed(url, "mock_path not provided")

    try:
        with open(mock_path, "r", encoding="utf-8", errors="replace") as fh:
            html_content = fh.read()
    except FileNotFoundError:
        return _failed(url, f"Mock file not found: {mock_path}")
    except OSError as exc:
        return _failed(url, f"Could not read mock file: {exc}")

    return _process_html(url, html_content)


# ---------------------------------------------------------------------------
# Network fetch
# ---------------------------------------------------------------------------


def _fetch_html(url: str) -> tuple:
    """
    Make an HTTP GET request and return the raw response HTML.

    Returns a two-tuple:
    - (html_string, None)  on success
    - (None, reason_string) on any error

    Never raises — all exceptions are caught and converted to reason strings.

    Parameters
    ----------
    url : str
        The target URL.

    Returns
    -------
    tuple
        (html_str, None) or (None, error_reason)
    """
    try:
        response = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        return (response.text, None)

    except requests.exceptions.Timeout:
        return (None, "Request timed out after 10 seconds")

    except requests.exceptions.ConnectionError:
        return (None, "Connection error — host unreachable or DNS failure")

    except requests.exceptions.TooManyRedirects:
        return (None, "Too many redirects")

    except requests.exceptions.HTTPError as exc:
        return (None, f"HTTP error: {exc.response.status_code}")

    except requests.exceptions.MissingSchema:
        return (None, "Invalid URL — missing scheme (http/https)")

    except requests.exceptions.InvalidURL:
        return (None, "Invalid URL format")

    except requests.exceptions.RequestException as exc:
        return (None, f"Request failed: {exc}")


# ---------------------------------------------------------------------------
# HTML processing pipeline
# ---------------------------------------------------------------------------


def _process_html(url: str, html: str) -> dict:
    """
    Validate raw HTML for JavaScript gating, then parse and clean it.

    Checks content length and JS-gate phrases before parsing. If either
    check fails, returns a limited_access dict without crashing.

    Parameters
    ----------
    url : str
        The source URL (for result attribution).
    html : str
        Raw HTML string to process.

    Returns
    -------
    dict
        success, limited_access, or failed dict.
    """
    # Guard: suspiciously short content
    if len(html.strip()) < _MIN_CONTENT_LENGTH:
        return _limited_access(url, "Page content too short — likely a redirect or error page")

    # Guard: JavaScript-gated page detection
    html_lower = html.lower()
    for signal in _JS_SIGNALS:
        if signal in html_lower:
            # Future: integrate Playwright or external rendering service for JS-heavy sites
            return _limited_access(url, "JavaScript-heavy or protected site")

    title, text = _parse_html(html)
    cleaned = _clean_text(text)
    word_count = _count_words(cleaned)

    # Even after parsing, very short extracted text indicates a JS-rendered page
    if word_count == 0 or len(cleaned) < _MIN_CONTENT_LENGTH:
        return _limited_access(url, "JavaScript-heavy or protected site")

    return {
        "status": "success",
        "url": url,
        "html": html,
        "text": cleaned,
        "title": title,
        "word_count": word_count,
    }


def _parse_html(html: str) -> tuple:
    """
    Parse raw HTML with BeautifulSoup and extract the page title and visible text.

    Removes script, style, noscript, head, meta, and link tags before
    extracting text to avoid polluting the content analysis with code
    or invisible metadata.

    Parameters
    ----------
    html : str
        Raw HTML string.

    Returns
    -------
    tuple
        (title: str, visible_text: str)
        Both values are always strings — empty string if not found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip non-visible tags in place
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract all remaining visible text
    raw_text = soup.get_text(separator="\n")

    return title, raw_text


def _clean_text(text: str) -> str:
    """
    Normalise raw extracted text into clean, readable prose.

    Steps:
    1. Strip leading/trailing whitespace from each line
    2. Remove lines that are blank or contain only punctuation/symbols
    3. Collapse runs of more than two consecutive blank lines to one
    4. Collapse multiple spaces within a line to a single space

    Parameters
    ----------
    text : str
        Raw text extracted from BeautifulSoup .get_text().

    Returns
    -------
    str
        Cleaned text string suitable for word counting and scoring.
    """
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        # Drop lines that are empty or contain only whitespace/punctuation
        if not line or re.match(r"^[\s\W]+$", line):
            continue
        # Collapse internal whitespace
        line = re.sub(r"[ \t]+", " ", line)
        cleaned_lines.append(line)

    # Rejoin and collapse runs of more than 2 consecutive blank lines
    joined = "\n".join(cleaned_lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)

    return joined.strip()


def _count_words(text: str) -> int:
    """
    Count the number of whitespace-delimited words in a cleaned text string.

    Parameters
    ----------
    text : str
        Cleaned visible text.

    Returns
    -------
    int
        Word count. Returns 0 for empty or whitespace-only input.
    """
    if not text or not text.strip():
        return 0
    return len(text.split())


# ---------------------------------------------------------------------------
# Result constructors (keep return shapes DRY)
# ---------------------------------------------------------------------------


def _limited_access(url: str, reason: str) -> dict:
    """
    Return a standardised limited_access result dict.

    Parameters
    ----------
    url : str
        The page URL.
    reason : str
        Human-readable explanation of why full access was not possible.

    Returns
    -------
    dict
    """
    return {
        "status": "limited_access",
        "reason": reason,
        "url": url,
        "html": None,
        "text": None,
        "title": None,
        "word_count": 0,
    }


def _failed(url: str, reason: str) -> dict:
    """
    Return a standardised failed result dict.

    Parameters
    ----------
    url : str
        The page URL (or attempted URL).
    reason : str
        Human-readable explanation of the failure.

    Returns
    -------
    dict
    """
    return {
        "status": "failed",
        "reason": reason,
        "url": url,
        "html": None,
        "text": None,
        "title": None,
        "word_count": 0,
    }