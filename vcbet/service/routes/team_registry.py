from __future__ import annotations

from fastapi import FastAPI, HTTPException

from vcbet.service.schemas import (
    TeamRegistryAliasRequest,
    TeamRegistrySyncAllRequest,
    TeamRegistrySyncRequest,
)
from vcbet.service.team_registry_api import (
    approve_registry_alias,
    load_approved_registry_aliases,
    load_pending_registry_reviews,
    list_registry_leagues,
    reject_registry_alias,
    sync_all_registry_leagues,
    sync_registry_league,
    update_registry_pending_alias,
)

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/team-registry/pending")
    def get_team_registry_pending():
        return load_pending_registry_reviews(ctx.settings.project_root)

    @app.get("/api/team-registry/approved")
    def get_team_registry_approved():
        return load_approved_registry_aliases(ctx.settings.project_root)

    @app.get("/api/team-registry/leagues")
    def get_team_registry_leagues():
        return list_registry_leagues(ctx.settings.project_root)

    @app.post("/api/team-registry/sync")
    def sync_team_registry(req: TeamRegistrySyncRequest):
        try:
            result = sync_registry_league(ctx.settings.project_root, req.dict(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if result.get("status") == "error":
            raise HTTPException(status_code=502, detail=result)
        return result

    @app.post("/api/team-registry/sync-all")
    def sync_all_team_registry(req: TeamRegistrySyncAllRequest | None = None):
        payload = req.dict(exclude_none=True) if req else {}
        return sync_all_registry_leagues(ctx.settings.project_root, payload)

    @app.post("/api/team-registry/approve")
    def approve_team_registry_alias(req: TeamRegistryAliasRequest):
        try:
            return approve_registry_alias(ctx.settings.project_root, req.dict(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/team-registry/reject")
    def reject_team_registry_alias(req: TeamRegistryAliasRequest):
        return reject_registry_alias(ctx.settings.project_root, req.dict(exclude_none=True))

    @app.post("/api/team-registry/update")
    def update_team_registry_alias(req: TeamRegistryAliasRequest):
        try:
            return update_registry_pending_alias(ctx.settings.project_root, req.dict(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
