from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/entities/replays")
    def entity_replays(limit: int = Query(300)):
        catalog = ctx.settings.project_root / "data" / "replays" / "catalog.jsonl"
        refresh_status = ctx.refresh_catalog_if_needed("replays")
        records, status = ctx.read_jsonl_catalog(catalog)
        items = []
        for item in ctx.active_catalog_items(records, "replay_dir")[:ctx.safe_limit(limit)]:
            normalized = {
                "replay_id": item.get("replay_id") or Path(str(item.get("replay_dir") or "")).name,
                "label": ctx.replay_label(item),
                "target_date": item.get("target_date"),
                "created_at": item.get("created_at"),
                "status": item.get("status"),
                "configs": item.get("configs") or [],
                "replay_dir": item.get("replay_dir"),
                "replay_mode": item.get("replay_mode"),
                "replay_strength": item.get("replay_strength"),
                "summary_file": item.get("summary_file"),
                "source_run_dir": item.get("source_run_dir"),
            }
            items.append(normalized)
        message = None
        if status == "missing":
            message = "Catálogo não encontrado. Rode scripts/build_run_catalog.py e scripts/build_replay_catalog.py ou gere uma nova execução."
        return {"items": items, "status": status, "refresh_status": refresh_status, "catalog_file": "data/replays/catalog.jsonl", "message": message}

    @app.get("/replays/summaries")
    def list_replay_summaries(base_dir: str = Query("data/replays"), limit: int = 50):
        root = ctx.resolve_project_path(base_dir)
        if not root.exists():
            return {"items": [], "base_dir": base_dir}

        items = []
        for summary_file in root.rglob("comparison_summary.json"):
            try:
                payload = json.loads(summary_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            results = payload.get("results") or []
            items.append({
                "summary_file": str(summary_file.relative_to(ctx.settings.project_root)) if str(summary_file).startswith(str(ctx.settings.project_root)) else str(summary_file),
                "source_run_id": payload.get("source_run_id"),
                "target_date": payload.get("target_date"),
                "replay_input_contract": payload.get("replay_input_contract", {}),
                "replay_quality_status": payload.get("replay_quality_status") or (payload.get("replay_input_contract", {}) or {}).get("replay_quality_status"),
                "replay_source_strength": payload.get("replay_source_strength") or (payload.get("replay_input_contract", {}) or {}).get("replay_source_strength"),
                "temporal_contract_status": payload.get("temporal_contract_status") or (payload.get("replay_input_contract", {}) or {}).get("temporal_contract_status"),
                "replay_limitations": payload.get("replay_limitations") or (payload.get("replay_input_contract", {}) or {}).get("replay_limitations", []),
                "configs": [item.get("config_name") for item in results],
                "results_count": len(results),
                "mtime": summary_file.stat().st_mtime,
            })

        items.sort(key=lambda item: float(item.get("mtime") or 0), reverse=True)
        for item in items:
            item.pop("mtime", None)
        return {"items": items[:limit], "base_dir": base_dir}

    @app.get("/replays/summary")
    def get_replay_summary(summary_file: str):
        path = ctx.resolve_project_path(summary_file)
        if not path.exists():
            raise HTTPException(status_code=404, detail="summary não encontrado")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"erro ao ler summary: {exc}")

    @app.get("/replays/picks")
    def get_replay_picks(summary_file: str, config_name: str, limit: int = 500):
        summary_path = ctx.resolve_project_path(summary_file)
        if not summary_path.exists():
            raise HTTPException(status_code=404, detail="summary não encontrado")
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"erro ao ler summary: {exc}")

        selected = None
        for item in payload.get("results") or []:
            if item.get("config_name") == config_name:
                selected = item
                break
        if not selected:
            raise HTTPException(status_code=404, detail="config não encontrada nesse replay")

        replay_dir = Path(str(selected.get("replay_dir") or ""))
        if not replay_dir.is_absolute():
            replay_dir = (ctx.settings.project_root / replay_dir).resolve()

        source = ""
        rows: list[dict[str, str]] = []
        ledger_file = replay_dir / "replay_ledger.csv"
        picks_file = replay_dir / "picks_snapshot.csv"
        if ledger_file.exists():
            source = str(ledger_file.relative_to(ctx.settings.project_root)) if str(ledger_file).startswith(str(ctx.settings.project_root)) else str(ledger_file)
            rows = ctx.read_ledger_rows(ledger_file, limit=limit)
        elif picks_file.exists():
            source = str(picks_file.relative_to(ctx.settings.project_root)) if str(picks_file).startswith(str(ctx.settings.project_root)) else str(picks_file)
            rows = ctx.read_csv_rows(picks_file, limit=limit)

        items = [ctx.compact_pick_row(row) for row in rows]
        return {
            "summary_file": summary_file,
            "config_name": config_name,
            "source_file": source,
            "items": items,
            "total": len(items),
            "limit": limit,
        }
