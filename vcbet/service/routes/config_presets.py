from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel, Field

from vcbet.core import strategy_config

from . import RouteContext


CONFIG_NAME_RE = re.compile(r"^[a-z0-9_]+$")
PROTECTED_CONFIGS = {"legacy_v2", "gd_experimental_v1"}


class ConfigPresetCreateRequest(BaseModel):
    source_name: str | None = None
    name: str
    label: str | None = None
    description: str | None = None
    payload: dict[str, Any] | None = None


class ConfigPresetCloneRequest(BaseModel):
    name: str
    label: str | None = None
    description: str | None = None


def _configs_dir() -> Path:
    return strategy_config.CONFIGS_DIR.resolve()


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_configs_dir().parent))
    except ValueError:
        return str(path)


def _config_path(name: str) -> Path:
    _validate_config_name(name)
    root = _configs_dir()
    path = (root / f"{name}.json").resolve()
    if path.parent != root:
        raise HTTPException(status_code=400, detail="Nome de config inválido.")
    return path


def _validate_config_name(name: str) -> None:
    if not CONFIG_NAME_RE.fullmatch(str(name or "")):
        raise HTTPException(status_code=400, detail="name só pode conter [a-z0-9_]+.")


def _load_raw(name: str) -> tuple[dict[str, Any], Path]:
    path = _config_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Config não encontrada: {name}")
    try:
        raw, _source = strategy_config.load_raw_config_payload(config_name=name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Config inválida: {exc}") from exc
    return raw, path


def _issue_payload(issues: list[strategy_config.ConfigValidationIssue]) -> list[dict[str, str]]:
    return [issue.to_dict() for issue in issues]


def _validation_summary(payload: dict[str, Any], expected_name: str) -> dict[str, Any]:
    issues = strategy_config.validate_strategy_config_payload(payload, expected_name=expected_name)
    return {
        "valid": not any(issue.severity == "error" for issue in issues),
        "errors": [issue.to_dict() for issue in issues if issue.severity == "error"],
        "warnings": [issue.to_dict() for issue in issues if issue.severity == "warning"],
        "issues": _issue_payload(issues),
    }


def _raise_if_invalid(payload: dict[str, Any], expected_name: str) -> None:
    summary = _validation_summary(payload, expected_name)
    if not summary["valid"]:
        raise HTTPException(status_code=400, detail=summary)


def _json_safe_payload(payload: dict[str, Any], expected_name: str) -> dict[str, Any]:
    normalized = deepcopy(payload)
    metadata = normalized.setdefault("metadata", {})
    metadata["name"] = expected_name
    metadata.setdefault("label", expected_name)
    return normalized


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def _config_detail(name: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    raw, path = _load_raw(name)
    resolved = strategy_config.resolve_strategy_config_payload(raw, config_name=name)
    payload = {
        "name": name,
        "raw": raw,
        "resolved": resolved,
        "protected": name in PROTECTED_CONFIGS,
        "path": _relative_path(path),
        "schema_options": {
            "available_markets": list(strategy_config.AVAILABLE_MARKETS),
            "available_pricing_variants": list(strategy_config.AVAILABLE_PRICING_VARIANTS),
        },
        "validation": _validation_summary(raw, name),
    }
    if extra:
        payload.update(extra)
    return payload


def _list_presets() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(_configs_dir().glob("*.json")):
        name = path.stem
        try:
            raw, _source = strategy_config.load_raw_config_payload(config_name=name)
            resolved = strategy_config.resolve_strategy_config_payload(raw, config_name=name)
            runtime = strategy_config._build_runtime_config(resolved, source_path=str(path))
            metadata = resolved.get("metadata", {})
            updated_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
            items.append({
                "name": name,
                "label": metadata.get("label") or name,
                "description": metadata.get("description") or "",
                "path": _relative_path(path),
                "protected": name in PROTECTED_CONFIGS,
                "pricing_variant": runtime.pricing_variant,
                "enabled_markets": sorted(runtime.allowed_markets),
                "updated_at": updated_at,
            })
        except Exception as exc:
            items.append({
                "name": name,
                "label": name,
                "description": f"erro ao carregar: {exc}",
                "path": _relative_path(path),
                "protected": name in PROTECTED_CONFIGS,
                "pricing_variant": "",
                "enabled_markets": [],
                "updated_at": "",
            })
    return items


def _create_payload(req: ConfigPresetCreateRequest) -> dict[str, Any]:
    if req.payload is not None:
        payload = deepcopy(req.payload)
    elif req.source_name:
        payload, _source_path = _load_raw(req.source_name)
    else:
        payload = deepcopy(strategy_config.DEFAULT_CONFIG_PAYLOAD)
    payload = _json_safe_payload(payload, req.name)
    payload["metadata"]["label"] = req.label or payload["metadata"].get("label") or req.name
    payload["metadata"]["description"] = req.description if req.description is not None else payload["metadata"].get("description", "")
    return payload


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/config-presets")
    def list_config_presets() -> list[dict[str, Any]]:
        return _list_presets()

    @app.get("/api/config-presets/{name}")
    def get_config_preset(name: str) -> dict[str, Any]:
        return _config_detail(name)

    @app.post("/api/config-presets")
    def create_config_preset(req: ConfigPresetCreateRequest) -> dict[str, Any]:
        _validate_config_name(req.name)
        path = _config_path(req.name)
        if path.exists():
            raise HTTPException(status_code=409, detail="Config já existe. Use PUT para sobrescrever.")
        payload = _create_payload(req)
        _raise_if_invalid(payload, req.name)
        _write_json_atomic(path, payload)
        return _config_detail(req.name)

    @app.put("/api/config-presets/{name}")
    def save_config_preset(name: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        path = _config_path(name)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Config não encontrada: {name}")
        raw = payload.get("raw") if isinstance(payload, dict) and isinstance(payload.get("raw"), dict) else payload
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Payload deve ser objeto JSON.")
        raw = _json_safe_payload(raw, name)
        _raise_if_invalid(raw, name)
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        try:
            _write_json_atomic(path, raw)
        except Exception:
            if backup_path.exists():
                shutil.copy2(backup_path, path)
            raise
        return _config_detail(name, extra={"backup_path": _relative_path(backup_path)})

    @app.delete("/api/config-presets/{name}")
    def delete_config_preset(name: str) -> dict[str, Any]:
        path = _config_path(name)
        if name in PROTECTED_CONFIGS:
            raise HTTPException(status_code=403, detail="Config protegida não pode ser deletada.")
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Config não encontrada: {name}")
        if path.parent != _configs_dir() or path.suffix != ".json":
            raise HTTPException(status_code=400, detail="Delete permitido apenas para configs/*.json.")
        path.unlink()
        return {"status": "deleted", "name": name}

    @app.post("/api/config-presets/{name}/validate")
    def validate_config_preset(name: str, payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        if payload is None:
            raw, _path = _load_raw(name)
        else:
            raw = payload.get("raw") if isinstance(payload, dict) and isinstance(payload.get("raw"), dict) else payload
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="Payload deve ser objeto JSON.")
        raw = _json_safe_payload(raw, name)
        return _validation_summary(raw, name)

    @app.post("/api/config-presets/{name}/clone")
    def clone_config_preset(name: str, req: ConfigPresetCloneRequest) -> dict[str, Any]:
        _validate_config_name(name)
        _validate_config_name(req.name)
        if _config_path(req.name).exists():
            raise HTTPException(status_code=409, detail="Config de destino já existe.")
        source, _source_path = _load_raw(name)
        payload = _json_safe_payload(source, req.name)
        payload["metadata"]["label"] = req.label or payload["metadata"].get("label") or req.name
        payload["metadata"]["description"] = req.description if req.description is not None else payload["metadata"].get("description", "")
        _raise_if_invalid(payload, req.name)
        _write_json_atomic(_config_path(req.name), payload)
        return _config_detail(req.name, extra={"source_name": name})
