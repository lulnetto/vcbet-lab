from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI

from vcbet.service.schemas import HealthResponse

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            project_root=str(ctx.settings.project_root),
            jobs_dir=str(ctx.settings.jobs_dir),
            logs_dir=str(ctx.settings.logs_dir),
            now=datetime.now(),
        )
