"""Thread-safe, shared resilient cache used by all dashboard clients."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Generic, Literal, TypeVar

T = TypeVar("T")
Freshness = Literal["fresh", "stale", "unavailable"]


@dataclass(frozen=True)
class CachedRead(Generic[T]):
    state: Freshness
    value: T | None
    fetched_at: datetime | None


@dataclass(frozen=True)
class CacheMetrics:
    hits: int
    misses: int
    last_success_at: datetime | None


class ResilientTtlCache(Generic[T]):
    def __init__(self, ttl_seconds: int, unavailable_after_seconds: int):
        self._ttl = timedelta(seconds=ttl_seconds)
        self._unavailable_after = timedelta(seconds=unavailable_after_seconds)
        self._value: T | None = None
        self._fetched_at: datetime | None = None
        self._hits = self._misses = 0
        self._lock = Lock()

    def get(self, loader: Callable[[], T], now: datetime | None = None) -> CachedRead[T]:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            if self._fetched_at and now - self._fetched_at < self._ttl:
                self._hits += 1
                return CachedRead("fresh", self._value, self._fetched_at)
            self._misses += 1
            try:
                value = loader()
            except Exception:
                if self._fetched_at and now - self._fetched_at < self._unavailable_after:
                    return CachedRead("stale", self._value, self._fetched_at)
                return CachedRead("unavailable", None, self._fetched_at)
            self._value, self._fetched_at = value, now
            return CachedRead("fresh", value, now)

    def metrics(self) -> CacheMetrics:
        with self._lock:
            return CacheMetrics(self._hits, self._misses, self._fetched_at)
