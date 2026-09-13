"""Application orchestration; intentionally independent of HTTP and AWS SDKs."""

from __future__ import annotations

from dashboard.app.application.cache import CachedRead, ResilientTtlCache
from dashboard.app.domain.models import DashboardReadRepository, PublicationSnapshot, PumpSnapshot


class DashboardQueryService:
    def __init__(self, repository: DashboardReadRepository, ttl_seconds: int = 10, unavailable_after_seconds: int = 45):
        self._repository = repository
        self._pumps = ResilientTtlCache[list[PumpSnapshot]](ttl_seconds, unavailable_after_seconds)
        self._publication = ResilientTtlCache[PublicationSnapshot](ttl_seconds, unavailable_after_seconds)

    def pumps(self) -> CachedRead[list[PumpSnapshot]]:
        return self._pumps.get(self._repository.fetch_pumps)

    def publication(self) -> CachedRead[PublicationSnapshot]:
        return self._publication.get(self._repository.fetch_latest_publication)

    def metrics(self) -> dict:
        return {"pump_cache": self._pumps.metrics(), "publication_cache": self._publication.metrics()}
