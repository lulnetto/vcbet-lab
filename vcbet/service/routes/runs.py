from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Query

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/api/entities/runs")
    def entity_runs(limit: int = Query(300)):
        catalog = ctx.settings.project_root / "data" / "runs" / "catalog.jsonl"
        refresh_status = ctx.refresh_catalog_if_needed("runs")
        records, status = ctx.read_jsonl_catalog(catalog)
        items = []
        for item in ctx.active_catalog_items(records, "run_dir")[:ctx.safe_limit(limit)]:
            normalized = {
                "run_id": item.get("run_id") or Path(str(item.get("run_dir") or "")).name,
                "label": ctx.run_label(item),
                "target_date": item.get("target_date"),
                "created_at": item.get("created_at"),
                "config_name": item.get("config_name"),
                "status": item.get("status"),
                "picks_rows": item.get("picks_rows"),
                "run_dir": item.get("run_dir"),
                "path": item.get("run_dir"),
                "run_mode": item.get("run_mode"),
            }
            items.append(normalized)
        message = None
        if status == "missing":
            message = "Catálogo não encontrado. Rode scripts/build_run_catalog.py e scripts/build_replay_catalog.py ou gere uma nova execução."
        return {"items": items, "status": status, "refresh_status": refresh_status, "catalog_file": "data/runs/catalog.jsonl", "message": message}

    @app.get("/runs")
    def list_source_runs(base_dir: str = Query("data/runs"), limit: int = 200):
        root = ctx.resolve_project_path(base_dir)
        if not root.exists():
            return {"items": [], "base_dir": base_dir}

        items = []
        for run_dir in root.glob("*/*"):
            if not run_dir.is_dir():
                continue
            odds_file = run_dir / "odds_snapshot.csv"
            xg_file = run_dir / "xg_snapshot.csv"
            if not odds_file.exists() or not xg_file.exists():
                continue
            manifest_file = run_dir / "run_manifest.json"
            manifest = {}
            if manifest_file.exists():
                try:
                    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
            items.append({
                "run_id": manifest.get("run_id") or run_dir.name,
                "target_date": manifest.get("target_date") or run_dir.parent.name,
                "path": str(run_dir.relative_to(ctx.settings.project_root)) if str(run_dir).startswith(str(ctx.settings.project_root)) else str(run_dir),
                "picks_rows": manifest.get("picks_rows"),
                "status": manifest.get("status"),
                "odds_snapshot_time": manifest.get("odds_snapshot_time"),
                "xg_asof": manifest.get("xg_asof"),
                "temporal_contract_status": manifest.get("temporal_contract_status"),
                "mtime": run_dir.stat().st_mtime,
            })

        items.sort(key=lambda item: (str(item.get("target_date") or ""), float(item.get("mtime") or 0)), reverse=True)
        for item in items:
            item.pop("mtime", None)
        return {"items": items[:limit], "base_dir": base_dir}
