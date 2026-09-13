"""HTTP presentation layer; contains no AWS client calls or cache internals."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dashboard.app.application.cache import CachedRead
from dashboard.app.application.service import DashboardQueryService
from dashboard.app.domain.models import PUMP_IDS
from dashboard.app.presentation.schemas import Envelope, HealthDto, PublicationDto, PumpDto

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def get_service(request: Request) -> DashboardQueryService:
    return request.app.state.dashboard_service


def envelope(read: CachedRead, data) -> Envelope:
    fetched = read.fetched_at
    age = None if fetched is None else max(0, int((datetime.now(timezone.utc) - fetched).total_seconds()))
    return Envelope(state=read.state, fetched_at=fetched.isoformat().replace("+00:00", "Z") if fetched else None, data_age_seconds=age, data=data)


def unavailable_if_needed(read: CachedRead) -> None:
    if read.state == "unavailable":
        # A stable generic message avoids leaking provider/credential details.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="dependency unavailable")


@router.get("/pumps", response_model=Envelope)
def list_pumps(service: DashboardQueryService = Depends(get_service)):
    read = service.pumps()
    unavailable_if_needed(read)
    return envelope(read, [PumpDto.model_validate(item.__dict__) for item in read.value or []])


@router.get("/pumps/{esp_id}", response_model=Envelope)
def get_pump(esp_id: str, service: DashboardQueryService = Depends(get_service)):
    if esp_id not in PUMP_IDS:
        raise HTTPException(status_code=404, detail="unknown pump")
    read = service.pumps()
    unavailable_if_needed(read)
    item = next((pump for pump in read.value or [] if pump.esp_id == esp_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="pump has no latest state")
    return envelope(read, PumpDto.model_validate(item.__dict__))


@router.get("/kpis/latest", response_model=Envelope)
def latest_kpis(service: DashboardQueryService = Depends(get_service)):
    read = service.publication()
    unavailable_if_needed(read)
    data = PublicationDto.model_validate(read.value.__dict__) if read.value else None
    return envelope(read, data)


@router.get("/health", response_model=HealthDto)
def health(request: Request, service: DashboardQueryService = Depends(get_service)):
    def safe(metric):
        return {"hits": metric.hits, "misses": metric.misses, "last_success_at": metric.last_success_at.isoformat().replace("+00:00", "Z") if metric.last_success_at else None}
    metrics = service.metrics()
    return HealthDto(mode=request.app.state.settings.mode, pump_cache=safe(metrics["pump_cache"]), publication_cache=safe(metrics["publication_cache"]))
