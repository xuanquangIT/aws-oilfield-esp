"""Composition root and ASGI entry point for the loopback-only dashboard API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dashboard.app.application.service import DashboardQueryService
from dashboard.app.core.config import Settings
from dashboard.app.infrastructure.aws_repository import AwsDashboardRepository
from dashboard.app.infrastructure.fixture_repository import FixtureDashboardRepository
from dashboard.app.presentation.router import router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(settings: Settings | None = None, repository=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.host != "127.0.0.1":
        raise ValueError("Dashboard API must bind to 127.0.0.1")
    if repository is None:
        repository = FixtureDashboardRepository(settings.fixture_state) if settings.mode == "fixture" else AwsDashboardRepository(settings.aws_region, settings.aws_profile, settings.core_stack_name)
    app = FastAPI(title="Oilfield ESP Dashboard API", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.dashboard_service = DashboardQueryService(repository, settings.cache_ttl_seconds, settings.unavailable_after_seconds)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
        return response

    @app.exception_handler(Exception)
    async def unhandled_error(_request: Request, _error: Exception):
        return JSONResponse(status_code=500, content={"detail": "internal service error"})

    app.include_router(router)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        async def root():
            index_path = STATIC_DIR / "index.html"
            if index_path.is_file():
                return FileResponse(str(index_path))
            return JSONResponse({"message": "ESP Dashboard UI static assets pending"})

    return app
