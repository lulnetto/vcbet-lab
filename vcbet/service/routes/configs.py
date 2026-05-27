from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from vcbet.core.strategy_config import list_available_configs
from vcbet.service.schemas import ConfigInfo

from . import RouteContext


PROFILE_LEDGER_BINDINGS_FILE = "profile_ledger_bindings.json"
DEFAULT_PROFILE_LEDGER_BINDINGS = {
    "profile_conservative": "data/ledgers/conservative_bets_ledger.csv",
    "profile_standard": "data/ledgers/standard_bets_ledger.csv",
    "profile_aggressive": "data/ledgers/aggressive_bets_ledger.csv",
}


def _bindings_path(ctx: RouteContext) -> Path:
    return ctx.settings.project_root / "configs" / PROFILE_LEDGER_BINDINGS_FILE


def _load_profile_ledger_bindings(ctx: RouteContext) -> dict[str, str]:
    path = _bindings_path(ctx)
    if not path.exists():
        return dict(DEFAULT_PROFILE_LEDGER_BINDINGS)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"profile ledger bindings inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="profile ledger bindings deve ser um objeto JSON.")
    return {str(key): str(value) for key, value in payload.items() if str(key).strip() and str(value).strip()}


def _write_profile_ledger_bindings(ctx: RouteContext, bindings: dict[str, str]) -> None:
    path = _bindings_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(bindings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
        items = []
        seen_paths: set[str] = set()

        def add_ledger(*, ledger_id: str, label: str, path: str, mode: str, exists: bool) -> None:
            if path in seen_paths:
                return
            seen_paths.add(path)
            items.append({
                "id": ledger_id,
                "label": label,
                "path": path,
                "mode": mode,
                "exists": exists,
            })

        official = ctx.settings.project_root / "data" / "history" / "bets_ledger.csv"
        add_ledger(
            ledger_id="official",
            label="Oficial",
            path="data/history/bets_ledger.csv",
            mode="official",
            exists=official.exists(),
        )
        history = ctx.settings.project_root / "data" / "history"
        if history.exists():
            for candidate in sorted(history.glob("*ledger*.csv")):
                rel = ctx.project_rel(candidate)
                if rel == "data/history/bets_ledger.csv" or "data/_archive/" in rel:
                    continue
                add_ledger(
                    ledger_id=candidate.stem,
                    label=candidate.stem.replace("_", " ").title(),
                    path=rel,
                    mode="sandbox",
                    exists=True,
                )
        ledgers_dir = ctx.settings.project_root / "data" / "ledgers"
        if ledgers_dir.exists():
            for candidate in sorted(ledgers_dir.glob("*ledger*.csv")):
                rel = ctx.project_rel(candidate)
                add_ledger(
                    ledger_id=candidate.stem,
                    label=candidate.stem.replace("_", " ").title(),
                    path=rel,
                    mode="profile",
                    exists=True,
                )
        for config_name, ledger_path in _load_profile_ledger_bindings(ctx).items():
            resolved = ctx.resolve_project_path(ledger_path)
            add_ledger(
                ledger_id=config_name,
                label=config_name.replace("_", " ").title(),
                path=ledger_path,
                mode="profile_binding",
                exists=resolved.exists(),
            )
        return {"items": items, "status": "ok"}

    @app.get("/api/profile-ledger-bindings")
    def get_profile_ledger_bindings():
        path = _bindings_path(ctx)
        return {
            "items": _load_profile_ledger_bindings(ctx),
            "path": ctx.project_rel(path),
            "exists": path.exists(),
            "status": "ok",
        }

    @app.post("/api/profile-ledger-bindings")
    def save_profile_ledger_bindings(payload: dict[str, Any] = Body(...)):
        raw = payload.get("items") if isinstance(payload, dict) and isinstance(payload.get("items"), dict) else payload
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Payload deve ser um objeto JSON.")
        bindings = {str(key).strip(): str(value).strip() for key, value in raw.items() if str(key).strip() and str(value).strip()}
        _write_profile_ledger_bindings(ctx, bindings)
        return {
            "items": bindings,
            "path": ctx.project_rel(_bindings_path(ctx)),
            "exists": True,
            "status": "ok",
        }
