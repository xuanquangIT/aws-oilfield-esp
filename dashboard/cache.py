"""Shared TTL cache with explicit fresh/stale/unavailable semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T | None = None
    fetched_at: datetime | None = None
    hits: int = 0
    misses: int = 0


class RefreshCache(Generic[T]):
    def __init__(self, ttl_seconds: int = 10, unavailable_after_seconds: int = 45):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.unavailable_after = timedelta(seconds=unavailable_after_seconds)
        self.entry: CacheEntry[T] = CacheEntry()

    def read(self, loader: Callable[[], T], now: datetime | None = None) -> tuple[str, T | None, datetime | None]:
        now = now or datetime.now(timezone.utc)
        if self.entry.fetched_at and now - self.entry.fetched_at < self.ttl:
            self.entry.hits += 1
            return "fresh", self.entry.value, self.entry.fetched_at
        self.entry.misses += 1
        try:
            value = loader()
        except Exception:
            if self.entry.fetched_at and now - self.entry.fetched_at < self.unavailable_after:
                return "stale", self.entry.value, self.entry.fetched_at
            return "unavailable", None, self.entry.fetched_at
        self.entry.value, self.entry.fetched_at = value, now
        return "fresh", value, now
