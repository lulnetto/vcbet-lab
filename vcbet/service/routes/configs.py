from __future__ import annotations

from fastapi import FastAPI

from vcbet.core.strategy_config import list_available_configs
from vcbet.service.schemas import ConfigInfo

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/configs", response_model=list[ConfigInfo])
    def get_configs() -> list[ConfigInfo]:
        return [ConfigInfo(**item) for item in list_available_configs()]

    @app.get("/api/entities/configs")
    def entity_configs():
        items = []
        for cfg in list_available_configs():
            name = cfg.get("name") or cfg.get("id")
            items.append({
                "id": name,
                "name": name,
                "label": cfg.get("label") or name,
                "description": cfg.get("description") or "",
                "path": cfg.get("path"),
                "fingerprint": cfg.get("fingerprint"),
                "is_default": name == "legacy_v2",
            })
        return {"items": items, "status": "ok"}

    @app.get("/api/entities/ledgers")
    def entity_ledgers():
        official = ctx.settings.project_root / "data" / "history" / "bets_ledger.csv"
        items = [{
            "id": "official",
            "label": "Oficial",
            "path": "data/history/bets_ledger.csv",
            "mode": "official",
            "exists": official.exists(),
        }]
        history = ctx.settings.project_root / "data" / "history"
        if history.exists():
            for candidate in sorted(history.glob("*ledger*.csv")):
                rel = ctx.project_rel(candidate)
                if rel == "data/history/bets_ledger.csv" or "data/_archive/" in rel:
                    continue
                items.append({
                    "id": candidate.stem,
                    "label": candidate.stem.replace("_", " ").title(),
                    "path": rel,
                    "mode": "sandbox",
                    "exists": True,
                })
        return {"items": items, "status": "ok"}
