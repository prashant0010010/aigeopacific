"""
core/storage.py
---------------
Local JSON-based audit history for AiGeoPacific.

Persists AuditResult objects as JSON files under ~/.aigeopacific/audits/.
No database required — designed for single-user local use in Phase 2.

Design decisions:
- Storage directory created on first write (never pre-assumed to exist).
- Corrupted or unreadable JSON files are skipped with a warning log —
  they never crash the application.
- Maximum 50 files enforced on every save (oldest pruned automatically).
- Serialisation uses Pydantic's model_dump(mode="json") for datetime safety.
- Deserialisation uses AuditResult.model_validate() for type safety.
- File naming: {url_slug}_{iso_timestamp}.json
  Example: ahrefs.com_2026-04-12T14-30-00.json

Imported by:
  - app.py: save after every audit, load on history click
  - ui/history_view.py: list_audits() for sidebar display
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.models import AuditMeta, AuditResult

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Storage configuration
# ------------------------------------------------------------------

_STORAGE_DIR = Path.home() / ".aigeopacific" / "audits"
_MAX_AUDITS = 50


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _ensure_storage_dir() -> Path:
    """
    Create the storage directory if it does not exist.

    Returns:
        Path to the storage directory.
    """
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORAGE_DIR


def _url_to_slug(url: str) -> str:
    """
    Convert a URL into a safe, readable filename slug.

    Strips scheme and www, then replaces non-alphanumeric characters
    with hyphens. Truncated to 60 characters to stay within filesystem limits.

    Args:
        url: Full URL string (e.g. "https://www.ahrefs.com/blog/seo-tips/")

    Returns:
        Slug string (e.g. "ahrefs.com-blog-seo-tips")
    """
    # Strip scheme
    slug = re.sub(r'^https?://', '', url.lower())
    # Strip www.
    slug = re.sub(r'^www\.', '', slug)
    # Replace non-alphanumeric (keep dots and hyphens) with hyphens
    slug = re.sub(r'[^a-z0-9.\-]', '-', slug)
    # Collapse consecutive hyphens
    slug = re.sub(r'-{2,}', '-', slug)
    # Strip trailing hyphens/dots
    slug = slug.strip('-.')
    return slug[:60]


def _timestamp_to_filename_part(ts: datetime) -> str:
    """
    Format a datetime as a filename-safe ISO string.

    Colons are replaced with hyphens so the string is valid on all OSes.

    Args:
        ts: Aware or naive datetime object.

    Returns:
        String like "2026-04-12T14-30-00"
    """
    return ts.strftime("%Y-%m-%dT%H-%M-%S")


def _build_file_path(url: str, timestamp: datetime) -> Path:
    """
    Construct the full file path for an audit JSON file.

    Args:
        url:       The audited URL.
        timestamp: The audit timestamp.

    Returns:
        Full Path object under _STORAGE_DIR.
    """
    slug = _url_to_slug(url)
    ts_part = _timestamp_to_filename_part(timestamp)
    filename = f"{slug}_{ts_part}.json"
    return _STORAGE_DIR / filename


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def save_audit(result: AuditResult) -> str:
    """
    Serialise an AuditResult to a JSON file and return its path.

    Automatically prunes old files if the total exceeds _MAX_AUDITS.
    If the directory cannot be created or the file cannot be written,
    a warning is logged and an empty string is returned (never raises).

    Args:
        result: Completed AuditResult object (post-scoring, post-enrichment).

    Returns:
        Absolute file path as a string, or "" on failure.
    """
    try:
        storage_dir = _ensure_storage_dir()
        ts = result.timestamp if result.timestamp else datetime.now(timezone.utc)
        file_path = _build_file_path(result.url, ts)

        # Serialise — mode="json" ensures datetime -> ISO string, etc.
        payload = result.model_dump(mode="json")

        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        logger.info("Audit saved: %s", file_path)

        # Prune after saving so the new file counts toward the limit
        prune_to_limit(_MAX_AUDITS)

        return str(file_path)

    except Exception as exc:
        logger.warning("Failed to save audit for %s: %s", result.url, exc)
        return ""


def load_audit(file_path: str) -> Optional[AuditResult]:
    """
    Deserialise an AuditResult from a JSON file.

    Handles missing files and corrupted JSON gracefully — returns None
    and logs a warning rather than raising.

    Args:
        file_path: Absolute or relative path to the JSON audit file.

    Returns:
        AuditResult object, or None if loading fails.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("Audit file not found: %s", file_path)
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return AuditResult.model_validate(data)

    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("Corrupted audit file skipped (%s): %s", file_path, exc)
        return None


def list_audits() -> list[AuditMeta]:
    """
    Return metadata for all saved audits, sorted newest-first.

    Corrupted or unreadable files are silently skipped.
    Does not load full AuditResult objects — only reads the minimal
    fields needed for the history sidebar (url, timestamp, cqs, confidence).

    Returns:
        List of AuditMeta objects, newest first.
    """
    try:
        storage_dir = _ensure_storage_dir()
    except Exception as exc:
        logger.warning("Cannot access storage directory: %s", exc)
        return []

    metas: list[AuditMeta] = []

    for json_file in sorted(storage_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(json_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            # Extract only the fields needed for AuditMeta
            meta = AuditMeta(
                url=data["url"],
                timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                cqs=float(data.get("cqs", 0.0)),
                confidence_level=data.get("confidence_level", "Low"),
                file_path=str(json_file),
            )
            metas.append(meta)

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping corrupted audit file %s: %s", json_file.name, exc)
            continue

    return metas


def delete_audit(file_path: str) -> bool:
    """
    Delete a single audit JSON file.

    Args:
        file_path: Absolute path to the file to delete.

    Returns:
        True if deleted successfully, False if the file did not exist or deletion failed.
    """
    path = Path(file_path)
    try:
        if path.exists():
            path.unlink()
            logger.info("Audit deleted: %s", file_path)
            return True
        else:
            logger.warning("Cannot delete — file not found: %s", file_path)
            return False
    except Exception as exc:
        logger.warning("Failed to delete audit %s: %s", file_path, exc)
        return False


def prune_to_limit(limit: int = _MAX_AUDITS) -> None:
    """
    Delete the oldest audit files until the total count is within `limit`.

    Called automatically after every save_audit(). Can also be called
    manually to reclaim disk space.

    Files are sorted by filesystem modification time (oldest first).
    This matches wall-clock audit order even if timestamps in JSON differ.

    Args:
        limit: Maximum number of audit files to retain. Default: 50.
    """
    try:
        storage_dir = _ensure_storage_dir()
    except Exception as exc:
        logger.warning("Cannot prune — storage directory inaccessible: %s", exc)
        return

    all_files = sorted(
        storage_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
    )  # oldest first

    excess = len(all_files) - limit
    if excess <= 0:
        return

    for old_file in all_files[:excess]:
        try:
            old_file.unlink()
            logger.info("Pruned old audit: %s", old_file.name)
        except Exception as exc:
            logger.warning("Could not prune %s: %s", old_file.name, exc)


def storage_stats() -> dict:
    """
    Return a summary of current storage usage.

    Useful for debugging and the history panel footer.

    Returns:
        Dict with keys: count, limit, storage_dir, oldest_ts, newest_ts
    """
    try:
        storage_dir = _ensure_storage_dir()
        files = sorted(storage_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        count = len(files)
        return {
            "count": count,
            "limit": _MAX_AUDITS,
            "storage_dir": str(storage_dir),
            "oldest_ts": datetime.fromtimestamp(files[0].stat().st_mtime).isoformat() if files else None,
            "newest_ts": datetime.fromtimestamp(files[-1].stat().st_mtime).isoformat() if files else None,
        }
    except Exception as exc:
        logger.warning("storage_stats failed: %s", exc)
        return {"count": 0, "limit": _MAX_AUDITS, "storage_dir": str(_STORAGE_DIR)}