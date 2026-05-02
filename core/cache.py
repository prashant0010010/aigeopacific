"""
core/cache.py
-------------
Simple in-memory TTL (time-to-live) cache for AiGeoPacific.

Used primarily by search_service.py to cache DuckDuckGo query results,
preventing rate-limiting during demos and repeated audits of the same domain.

Design decisions:
- Module-level instances only — never a global singleton shared across services.
  Each service that needs caching creates its own TTLCache instance.
- No external dependencies (no Redis, no diskcache) — pure stdlib.
- Thread-safe reads/writes via threading.Lock (ThreadPoolExecutor in competitor.py
  means concurrent access is a real possibility).
- Does NOT use functools.lru_cache — it has no TTL support.
"""

import time
import threading
from typing import Any, Optional


class TTLCache:
    """
    In-memory key-value cache with per-entry time-to-live expiry.

    Entries older than `ttl_seconds` are treated as missing and
    evicted lazily on next access (no background sweep thread).

    Usage:
        _cache = TTLCache(ttl_seconds=3600)

        result = _cache.get("ddg:best seo tools")
        if result is None:
            result = expensive_search()
            _cache.set("ddg:best seo tools", result)
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        """
        Initialise the cache.

        Args:
            ttl_seconds: How long entries remain valid. Default 1 hour.
                         Set lower (e.g. 300) for volatile data.
        """
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")

        self._ttl: int = ttl_seconds
        # Internal store: key -> {"value": Any, "ts": float (epoch seconds)}
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value by key.

        Returns the value if present and not expired.
        Returns None if the key is missing or has expired.
        Expired entries are evicted on access (lazy eviction).

        Args:
            key: Cache key string.

        Returns:
            Cached value, or None if missing/expired.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            age = time.monotonic() - entry["ts"]
            if age > self._ttl:
                # Lazy eviction
                del self._store[key]
                return None

            return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """
        Store a value under the given key with the current timestamp.

        Overwrites any existing entry for that key, resetting its TTL.

        Args:
            key:   Cache key string. Convention: "ddg:{query}" for search results.
            value: Any picklable Python object. For search results, typically
                   a list[dict] returned by DuckDuckGo.
        """
        if not isinstance(key, str) or not key:
            raise ValueError("Cache key must be a non-empty string.")

        with self._lock:
            self._store[key] = {
                "value": value,
                "ts": time.monotonic(),
            }

    def delete(self, key: str) -> bool:
        """
        Remove a single entry from the cache.

        Args:
            key: Cache key to remove.

        Returns:
            True if the key existed and was removed, False if it was not present.
        """
        with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
            return existed

    def clear(self) -> None:
        """
        Remove all entries from the cache.

        Useful in tests to reset state between runs, or when the user
        explicitly requests a fresh audit with no cached data.
        """
        with self._lock:
            self._store.clear()

    # ------------------------------------------------------------------
    # Introspection helpers (useful for debugging / test assertions)
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Return the number of entries currently in the cache (including expired ones not yet evicted)."""
        with self._lock:
            return len(self._store)

    def is_alive(self, key: str) -> bool:
        """
        Check whether a key exists AND is within its TTL.

        Args:
            key: Cache key to test.

        Returns:
            True if the key is present and not expired.
        """
        return self.get(key) is not None

    def ttl_remaining(self, key: str) -> Optional[float]:
        """
        Return the seconds remaining before a key expires.

        Args:
            key: Cache key to inspect.

        Returns:
            Seconds remaining (float), or None if key is missing or already expired.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            remaining = self._ttl - (time.monotonic() - entry["ts"])
            return max(0.0, remaining) if remaining > 0 else None

    def __repr__(self) -> str:
        return f"TTLCache(ttl={self._ttl}s, entries={self.size()})"