from __future__ import annotations

from datetime import datetime
import csv
import json
from pathlib import Path
import subprocess

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import pandas as pd

from vcbet.core.ledger_manager import normalize_ledger_schema
from vcbet.core.strategy_config import ConfigResolutionError, list_available_configs
from .commands import (
    build_analysis_command,
    build_closing_odds_command,
    build_daily_commands,
    build_replay_command,
    build_replay_catalog_command,
    build_run_catalog_command,
    build_results_command,
    build_results_settlement_commands,
    build_settlement_command,
)
from .dashboard import apply_filters, build_dashboard_payload, load_ledger
from .job_runner import JobManager, ResourceBusyError
from .job_store import JobStore
from .schemas import (
    AliasApproveRequest,
    AnalysisRequest,
    ClosingOddsRequest,
    ConfigInfo,
    DailyRunRequest,
    HealthResponse,
    JobCreatedResponse,
    JobListResponse,
    ReplayRunRequest,
    ResultsCollectionRequest,
    ResultsSettlementRequest,
    SettlementRequest,
    TeamRegistryAliasRequest,
    TeamRegistrySyncAllRequest,
    TeamRegistrySyncRequest,
)
from .settings import ServiceSettings
from .team_registry_api import (
    approve_registry_alias,
    load_approved_registry_aliases,
    load_pending_registry_reviews,
    list_registry_leagues,
    reject_registry_alias,
    sync_all_registry_leagues,
    sync_registry_league,
    update_registry_pending_alias,
)

settings = ServiceSettings.load()
store = JobStore(settings.jobs_dir)
store.mark_interrupted_runs()
manager = JobManager(store, settings.logs_dir)

app = FastAPI(title="VCBet Service", version="0.5.0")

static_dir = settings.project_root / "vcbet" / "service" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def _resource_key(project_root: Path, ledger_file: str | None) -> str | None:
    if not ledger_file:
        return None
    path = Path(ledger_file)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    return str(path)


def _resolve_project_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (settings.project_root / path).resolve()
    return path


def _read_text_csv(path: Path) -> tuple[list[dict[str, str]], str, list[str]]:
    if not path.exists():
        return [], ";", []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    rows = [{str(k): "" if v is None else str(v) for k, v in row.items() if k is not None} for row in reader]
    fieldnames = list(reader.fieldnames or [])
    return rows, delimiter, fieldnames


def _write_text_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str], delimiter: str = ";") -> None:
    if not rows:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv_rows(path: Path, limit: int = 500) -> list[dict[str, str]]:
    rows, _, _ = _read_text_csv(path)
    return rows[:limit]


def _read_ledger_rows(path: Path, limit: int = 500) -> list[dict[str, str]]:
    if not path.exists():
        return []
    df = normalize_ledger_schema(pd.read_csv(path, sep=";")).head(limit).fillna("")
    return [{str(k): str(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _compact_pick_row(row: dict[str, str]) -> dict[str, str | float | None]:
    def pick(*names: str) -> str:
        for name in names:
            value = row.get(name)
            if value not in (None, ""):
                return str(value)
        return ""

    def num(*names: str) -> float | None:
        value = pick(*names)
        if not value:
            return None
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return None

    return {
        "league": pick("league"),
        "match_name": pick("match_name"),
        "market_type": pick("market_type"),
        "selection_raw": pick("selection_raw", "selection"),
        "target_team_name": pick("target_team_name", "team_name"),
        "line": num("line"),
        "odd_entrada": num("odd_entrada", "entry_odd", "odd"),
        "odd_justa": num("odd_justa", "fair_odd"),
        "ev_percent": num("ev_percent"),
        "pricing_signal_type": pick("pricing_signal_type"),
        "confidence_score": num("confidence_score"),
        "confidence_score_type": pick("confidence_score_type"),
        "confidence_score_scale": pick("confidence_score_scale"),
        "stake_units": num("stake_units"),
        "run_id": pick("run_id"),
        "config_name": pick("config_name", "strategy_config_name"),
        "config_fingerprint": pick("config_fingerprint", "strategy_config_fingerprint"),
        "source_run_id": pick("source_run_id"),
        "source_snapshot_ref": pick("source_snapshot_ref"),
        "odds_source_run_id": pick("odds_source_run_id"),
        "xg_source_run_id": pick("xg_source_run_id"),
        "odds_snapshot_hash": pick("odds_snapshot_hash"),
        "xg_snapshot_hash": pick("xg_snapshot_hash"),
        "odds_snapshot_time": pick("odds_snapshot_time"),
        "xg_asof": pick("xg_asof"),
        "temporal_contract_version": pick("temporal_contract_version"),
        "temporal_contract_status": pick("temporal_contract_status"),
        "decision_timestamp": pick("decision_timestamp", "generated_at"),
        "signal_version": pick("signal_version"),
        "pipeline_version": pick("pipeline_version"),
        "pick_safety_status": pick("pick_safety_status"),
        "candidate_stage": pick("candidate_stage"),
        "safety_gate_reason": pick("safety_gate_reason"),
        "decision_policy_status": pick("decision_policy_status"),
        "decision_reject_reason": pick("decision_reject_reason"),
        "selection_policy_status": pick("selection_policy_status"),
        "selection_reject_reason": pick("selection_reject_reason"),
        "portfolio_risk_status": pick("portfolio_risk_status"),
        "portfolio_risk_reason": pick("portfolio_risk_reason"),
        "portfolio_exposure_scope": pick("portfolio_exposure_scope"),
        "portfolio_exposure_after": num("portfolio_exposure_after"),
        "market_family": pick("market_family"),
        "final_bet_status": pick("final_bet_status", "status"),
        "closing_odd": num("closing_odd"),
        "closing_snapshot_time": pick("closing_snapshot_time"),
        "closing_update_status": pick("closing_update_status"),
        "result_units_model": num("result_units_model", "result_units"),
        "risk_flags": pick("risk_flags"),
    }


def _load_alias_map(alias_file: Path) -> dict[str, str]:
    if not alias_file.exists():
        return {}
    try:
        return json.loads(alias_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_alias_map(alias_file: Path, payload: dict[str, str]) -> None:
    alias_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _alias_candidate_files(scope: str = "runs_recent") -> list[Path]:
    candidates: list[Path] = []
    bases = [settings.project_root / "data" / "runs"]
    if scope == "replays":
        bases = [settings.project_root / "data" / "replays"]
    elif scope == "history":
        bases = [settings.project_root / "data" / "runs", settings.project_root / "data" / "replays"]
    for base in bases:
        if not base.exists():
            continue
        candidates.extend(base.rglob("alias_review_pending.csv"))
    return sorted(set(candidates))


def _normalize_alias_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for idx, row in enumerate(rows):
        clean = {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items()}
        clean["row_id"] = str(idx)
        clean.setdefault("match_status", "pending_review")
        clean.setdefault("source_name", "")
        clean.setdefault("suggestion", "")
        clean.setdefault("score", "")
        clean.setdefault("match_name", "")
        clean.setdefault("league", "")
        clean.setdefault("side", "")
        normalized.append(clean)
    return normalized


def _registry_approved_keys() -> set[tuple[str, str]]:
    approved = load_approved_registry_aliases(settings.project_root)
    return {
        (str(item.get("league") or ""), str(item.get("betano_name") or "").casefold())
        for item in approved.get("items", [])
    }


def _alias_file_payload(
    path: Path,
    include_blocked: bool = True,
    cleanup_empty: bool = True,
    include_resolved: bool = False,
    approved_keys: set[tuple[str, str]] | None = None,
) -> dict[str, object] | None:
    rows, delimiter, fieldnames = _read_text_csv(path)
    if not rows:
        if cleanup_empty and path.exists():
            path.unlink()
        return None

    normalized = _normalize_alias_rows(rows)
    visible = []
    covered = 0
    for row in normalized:
        is_active = row.get("match_status") == "pending_review" or (include_blocked and row.get("match_status") == "blocked")
        if approved_keys and (row.get("league", ""), row.get("source_name", "").casefold()) in approved_keys:
            covered += 1
            if include_resolved:
                visible.append({**row, "diagnostic_status": "covered_by_registry"})
            continue
        if is_active:
            visible.append(row)
    counts = {
        "pending_review": sum(1 for row in normalized if row.get("match_status") == "pending_review"),
        "blocked": sum(1 for row in normalized if row.get("match_status") == "blocked"),
    }
    if counts["pending_review"] == 0 and counts["blocked"] == 0:
        if cleanup_empty and path.exists():
            path.unlink()
        return None

    rel = str(path.relative_to(settings.project_root)) if str(path).startswith(str(settings.project_root)) else str(path)
    return {
        "pending_file": rel,
        "delimiter": delimiter,
        "fieldnames": fieldnames,
        "status_counts": counts,
        "covered_by_registry": covered,
        "items": visible,
        "total": len(visible),
    }


def _project_rel(path: Path) -> str:
    return str(path.relative_to(settings.project_root)) if str(path).startswith(str(settings.project_root)) else str(path)


def _read_jsonl_catalog(path: Path) -> tuple[list[dict[str, object]], str]:
    if not path.exists():
        return [], "missing"
    items: list[dict[str, object]] = []
    status = "ok"
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    status = "partial"
                    continue
                if isinstance(item, dict):
                    items.append(item)
    except Exception:
        return [], "unreadable"
    return items, status


def _catalog_source_paths(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [path for path in base.glob("*/*") if path.is_dir()]


def _catalog_is_stale(catalog: Path, source_base: Path) -> bool:
    if not catalog.exists():
        return True
    try:
        catalog_mtime = catalog.stat().st_mtime
    except OSError:
        return True
    for source_dir in _catalog_source_paths(source_base):
        try:
            newest = max(
                (path.stat().st_mtime for path in [source_dir, source_dir / "run_manifest.json"] if path.exists()),
                default=source_dir.stat().st_mtime,
            )
        except OSError:
            continue
        if newest > catalog_mtime:
            return True
    return False


def _refresh_catalog_if_needed(kind: str) -> str | None:
    if kind == "runs":
        catalog = settings.project_root / "data" / "runs" / "catalog.jsonl"
        source_base = settings.project_root / "data" / "runs"
        command = build_run_catalog_command(settings.project_root)
    elif kind == "replays":
        catalog = settings.project_root / "data" / "replays" / "catalog.jsonl"
        source_base = settings.project_root / "data" / "replays"
        command = build_replay_catalog_command(settings.project_root)
    else:
        return None
    if not _catalog_is_stale(catalog, source_base):
        return None
    try:
        subprocess.run(command.command, cwd=command.cwd, check=True, capture_output=True, text=True, timeout=30)
        return "refreshed"
    except Exception:
        return "refresh_failed"


def _format_date_label(value: object) -> str:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return text


def _format_time_label(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    normalized = text.replace(" ", "T")
    try:
        return datetime.fromisoformat(normalized).strftime("%H:%M")
    except ValueError:
        return text[11:16] if len(text) >= 16 else text


def _run_label(item: dict[str, object]) -> str:
    bits = [
        _format_date_label(item.get("target_date")),
        _format_time_label(item.get("created_at")),
        str(item.get("config_name") or item.get("run_mode") or "config ?"),
        f"{item.get('picks_rows')} picks" if item.get("picks_rows") not in (None, "") else "picks ?",
        str(item.get("status") or "status ?"),
    ]
    return " · ".join(bit for bit in bits if bit)


def _replay_label(item: dict[str, object]) -> str:
    configs = item.get("configs") or []
    config_count = len(configs) if isinstance(configs, list) else 1
    bits = [
        _format_date_label(item.get("target_date")),
        str(item.get("replay_strength") or item.get("replay_mode") or "replay"),
        f"{config_count} configs",
        str(item.get("status") or "status ?"),
    ]
    return " · ".join(bit for bit in bits if bit)


def _active_catalog_items(items: list[dict[str, object]], path_key: str) -> list[dict[str, object]]:
    active = []
    for item in items:
        path = str(item.get(path_key) or "")
        if not path or "data/_archive/" in path or path.startswith("data/_archive/"):
            continue
        active.append(item)
    return active


def _safe_limit(value: object, default: int = 300) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        project_root=str(settings.project_root),
        jobs_dir=str(settings.jobs_dir),
        logs_dir=str(settings.logs_dir),
        now=datetime.now(),
    )


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
    official = settings.project_root / "data" / "history" / "bets_ledger.csv"
    items = [{
        "id": "official",
        "label": "Oficial",
        "path": "data/history/bets_ledger.csv",
        "mode": "official",
        "exists": official.exists(),
    }]
    history = settings.project_root / "data" / "history"
    if history.exists():
        for candidate in sorted(history.glob("*ledger*.csv")):
            rel = _project_rel(candidate)
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


@app.get("/api/entities/runs")
def entity_runs(limit: int = Query(300)):
    catalog = settings.project_root / "data" / "runs" / "catalog.jsonl"
    refresh_status = _refresh_catalog_if_needed("runs")
    records, status = _read_jsonl_catalog(catalog)
    items = []
    for item in _active_catalog_items(records, "run_dir")[:_safe_limit(limit)]:
        normalized = {
            "run_id": item.get("run_id") or Path(str(item.get("run_dir") or "")).name,
            "label": _run_label(item),
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


@app.get("/api/entities/replays")
def entity_replays(limit: int = Query(300)):
    catalog = settings.project_root / "data" / "replays" / "catalog.jsonl"
    refresh_status = _refresh_catalog_if_needed("replays")
    records, status = _read_jsonl_catalog(catalog)
    items = []
    for item in _active_catalog_items(records, "replay_dir")[:_safe_limit(limit)]:
        normalized = {
            "replay_id": item.get("replay_id") or Path(str(item.get("replay_dir") or "")).name,
            "label": _replay_label(item),
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


@app.get("/runs")
def list_source_runs(base_dir: str = Query("data/runs"), limit: int = 200):
    root = _resolve_project_path(base_dir)
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
            "path": str(run_dir.relative_to(settings.project_root)) if str(run_dir).startswith(str(settings.project_root)) else str(run_dir),
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


@app.get("/replays/summaries")
def list_replay_summaries(base_dir: str = Query("data/replays"), limit: int = 50):
    root = _resolve_project_path(base_dir)
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
            "summary_file": str(summary_file.relative_to(settings.project_root)) if str(summary_file).startswith(str(settings.project_root)) else str(summary_file),
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
    path = _resolve_project_path(summary_file)
    if not path.exists():
        raise HTTPException(status_code=404, detail="summary não encontrado")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"erro ao ler summary: {exc}")


@app.get("/replays/picks")
def get_replay_picks(summary_file: str, config_name: str, limit: int = 500):
    summary_path = _resolve_project_path(summary_file)
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
        replay_dir = (settings.project_root / replay_dir).resolve()

    source = ""
    rows: list[dict[str, str]] = []
    ledger_file = replay_dir / "replay_ledger.csv"
    picks_file = replay_dir / "picks_snapshot.csv"
    if ledger_file.exists():
        source = str(ledger_file.relative_to(settings.project_root)) if str(ledger_file).startswith(str(settings.project_root)) else str(ledger_file)
        rows = _read_ledger_rows(ledger_file, limit=limit)
    elif picks_file.exists():
        source = str(picks_file.relative_to(settings.project_root)) if str(picks_file).startswith(str(settings.project_root)) else str(picks_file)
        rows = _read_csv_rows(picks_file, limit=limit)

    items = [_compact_pick_row(row) for row in rows]
    return {
        "summary_file": summary_file,
        "config_name": config_name,
        "source_file": source,
        "items": items,
        "total": len(items),
        "limit": limit,
    }


@app.get("/aliases/files")
def list_alias_files(include_blocked: bool = True, scope: str = "runs_recent", include_resolved: bool = False):
    items = []
    approved_keys = _registry_approved_keys()
    for file_path in _alias_candidate_files(scope=scope):
        payload = _alias_file_payload(
            file_path,
            include_blocked=include_blocked,
            cleanup_empty=True,
            include_resolved=include_resolved,
            approved_keys=approved_keys,
        )
        if not payload:
            continue
        if not include_resolved and int(payload.get("total") or 0) == 0:
            continue
        items.append({
            "pending_file": payload["pending_file"],
            "status_counts": payload["status_counts"],
            "total": payload["total"],
        })
    items.sort(key=lambda item: item["pending_file"], reverse=True)
    return {"items": items}


@app.get("/aliases/review")
def get_alias_review(pending_file: str, alias_file: str = "alias_times.json", include_blocked: bool = True, include_resolved: bool = False):
    pending_path = _resolve_project_path(pending_file)
    payload = _alias_file_payload(
        pending_path,
        include_blocked=include_blocked,
        cleanup_empty=False,
        include_resolved=include_resolved,
        approved_keys=_registry_approved_keys(),
    )
    if not payload:
        return {
            "pending_file": pending_file,
            "alias_file": alias_file,
            "status_counts": {"pending_review": 0, "blocked": 0},
            "items": [],
            "total": 0,
            "message": "sem aliases pendentes",
        }
    payload["alias_file"] = alias_file
    payload["alias_map_size"] = len(_load_alias_map(_resolve_project_path(alias_file)))
    return payload


@app.post("/aliases/approve")
def approve_aliases(req: AliasApproveRequest):
    pending_path = _resolve_project_path(req.pending_file)
    alias_path = _resolve_project_path(req.alias_file)
    rows, delimiter, fieldnames = _read_text_csv(pending_path)
    if not rows:
        if pending_path.exists():
            pending_path.unlink()
        return {"saved": 0, "remaining": 0, "deleted_pending_file": True}

    normalized = _normalize_alias_rows(rows)
    approvals_by_id = {item.row_id: item for item in req.approvals}
    alias_map = _load_alias_map(alias_path)

    remaining: list[dict[str, str]] = []
    saved = 0
    for row in normalized:
        approval = approvals_by_id.get(row["row_id"])
        if approval:
            target = approval.target_name.strip()
            source = approval.source_name.strip() or row.get("source_name", "").strip()
            if source and target:
                alias_map[source] = target
                saved += 1
            continue
        remaining_row = {k: v for k, v in row.items() if k != "row_id"}
        remaining.append(remaining_row)

    _save_alias_map(alias_path, alias_map)

    still_visible = [
        row for row in remaining
        if row.get("match_status") == "pending_review" or (req.include_blocked and row.get("match_status") == "blocked")
    ]
    deleted = not still_visible
    _write_text_csv(pending_path, remaining if still_visible else [], fieldnames, delimiter)

    return {
        "saved": saved,
        "remaining": len(still_visible),
        "deleted_pending_file": deleted,
        "alias_file": str(alias_path),
    }


@app.get("/api/team-registry/pending")
def get_team_registry_pending():
    return load_pending_registry_reviews(settings.project_root)


@app.get("/api/team-registry/approved")
def get_team_registry_approved():
    return load_approved_registry_aliases(settings.project_root)


@app.get("/api/team-registry/leagues")
def get_team_registry_leagues():
    return list_registry_leagues(settings.project_root)


@app.post("/api/team-registry/sync")
def sync_team_registry(req: TeamRegistrySyncRequest):
    try:
        result = sync_registry_league(settings.project_root, req.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/api/team-registry/sync-all")
def sync_all_team_registry(req: TeamRegistrySyncAllRequest | None = None):
    payload = req.dict(exclude_none=True) if req else {}
    return sync_all_registry_leagues(settings.project_root, payload)


@app.post("/api/team-registry/approve")
def approve_team_registry_alias(req: TeamRegistryAliasRequest):
    try:
        return approve_registry_alias(settings.project_root, req.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/team-registry/reject")
def reject_team_registry_alias(req: TeamRegistryAliasRequest):
    return reject_registry_alias(settings.project_root, req.dict(exclude_none=True))


@app.post("/api/team-registry/update")
def update_team_registry_alias(req: TeamRegistryAliasRequest):
    try:
        return update_registry_pending_alias(settings.project_root, req.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/dashboard/summary")
def dashboard_summary(
    ledger_file: str = Query("data/history/bets_ledger.csv"),
    run_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    league: str | None = None,
    market_type: str | None = None,
    only_executed: bool = False,
    only_settled: bool = False,
):
    try:
        df = load_ledger(_resolve_project_path(ledger_file))
        filtered = apply_filters(
            df,
            run_id=run_id,
            date_from=date_from,
            date_to=date_to,
            league=league,
            market_type=market_type,
            only_executed=only_executed,
            only_settled=only_settled,
        )
        payload = build_dashboard_payload(filtered)
        payload["applied_filters"] = {
            "ledger_file": ledger_file,
            "run_id": run_id,
            "date_from": date_from,
            "date_to": date_to,
            "league": league,
            "market_type": market_type,
            "only_executed": only_executed,
            "only_settled": only_settled,
        }
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"erro ao montar dashboard: {exc}")


@app.get("/dashboard/entries")
def dashboard_entries(
    ledger_file: str = Query("data/history/bets_ledger.csv"),
    run_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    league: str | None = None,
    market_type: str | None = None,
    only_executed: bool = False,
    only_settled: bool = False,
    limit: int = 100,
):
    try:
        df = load_ledger(_resolve_project_path(ledger_file))
        filtered = apply_filters(
            df,
            run_id=run_id,
            date_from=date_from,
            date_to=date_to,
            league=league,
            market_type=market_type,
            only_executed=only_executed,
            only_settled=only_settled,
        )
        payload = build_dashboard_payload(filtered, entries_limit=limit)
        return {
            "items": payload["entries"],
            "total_filtered": int(len(filtered)),
            "limit": limit,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"erro ao listar entradas: {exc}")


@app.get("/jobs", response_model=JobListResponse)
def list_jobs(limit: int = 50) -> JobListResponse:
    items = manager.list_jobs()[:limit]
    return JobListResponse(items=items)


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job não encontrado")
    return job


@app.get("/jobs/{job_id}/logs", response_class=PlainTextResponse)
def get_job_logs(job_id: str, lines: int = 200) -> str:
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job não encontrado")
    return manager.read_log_tail(job_id, lines=lines)


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job não encontrado")
    if not manager.cancel_job(job_id):
        return {"job_id": job_id, "cancelled": False, "message": "job não está rodando"}
    return {"job_id": job_id, "cancelled": True}


@app.post("/jobs/analysis", response_model=JobCreatedResponse)
def start_analysis(req: AnalysisRequest) -> JobCreatedResponse:
    try:
        command = build_analysis_command(settings.project_root, req)
        commands = [command, build_run_catalog_command(settings.project_root)]
        job = manager.submit_pipeline_job(
            title="Análise do dia",
            job_type="analysis",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            commands=commands,
            resource_key=_resource_key(settings.project_root, req.ledger_file),
        )
    except (ResourceBusyError, ConfigResolutionError) as exc:
        status = 409 if isinstance(exc, ResourceBusyError) else 400
        raise HTTPException(status_code=status, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.post("/jobs/closing-odds", response_model=JobCreatedResponse)
def start_closing_odds(req: ClosingOddsRequest) -> JobCreatedResponse:
    command = build_closing_odds_command(settings.project_root, req)
    try:
        job = manager.submit_command_job(
            title="Atualizar closing odds",
            job_type="closing_odds",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            command=command,
            resource_key=_resource_key(settings.project_root, req.ledger_file),
        )
    except ResourceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.post("/jobs/results-collection", response_model=JobCreatedResponse)
def start_results_collection(req: ResultsCollectionRequest) -> JobCreatedResponse:
    command = build_results_command(settings.project_root, req)
    try:
        job = manager.submit_command_job(
            title="Atualizar resultados",
            job_type="results_collection",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            command=command,
            resource_key=_resource_key(settings.project_root, req.ledger_file),
        )
    except ResourceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.post("/jobs/settlement", response_model=JobCreatedResponse)
def start_settlement(req: SettlementRequest) -> JobCreatedResponse:
    command = build_settlement_command(settings.project_root, req)
    try:
        job = manager.submit_command_job(
            title="Liquidar ledger",
            job_type="settlement",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            command=command,
            resource_key=_resource_key(settings.project_root, req.ledger_file),
        )
    except ResourceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.post("/jobs/results-settlement-cycle", response_model=JobCreatedResponse)
def start_results_settlement_cycle(req: ResultsSettlementRequest) -> JobCreatedResponse:
    commands = build_results_settlement_commands(settings.project_root, req)
    try:
        job = manager.submit_pipeline_job(
            title="Resultados + settlement",
            job_type="results_settlement_cycle",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            commands=commands,
            resource_key=_resource_key(settings.project_root, req.ledger_file),
        )
    except ResourceBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.post("/jobs/daily-run", response_model=JobCreatedResponse)
def start_daily_run(req: DailyRunRequest) -> JobCreatedResponse:
    try:
        commands = build_daily_commands(settings.project_root, req)
        if not commands:
            raise HTTPException(status_code=400, detail="daily-run sem passos habilitados")
        job = manager.submit_pipeline_job(
            title="Ciclo diário completo",
            job_type="daily_run",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            commands=commands,
            resource_key=_resource_key(settings.project_root, req.ledger_file),
        )
    except (ResourceBusyError, ConfigResolutionError) as exc:
        status = 409 if isinstance(exc, ResourceBusyError) else 400
        raise HTTPException(status_code=status, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.post("/jobs/replay-run", response_model=JobCreatedResponse)
def start_replay_run(req: ReplayRunRequest) -> JobCreatedResponse:
    try:
        command = build_replay_command(settings.project_root, req)
        commands = [command, build_replay_catalog_command(settings.project_root)]
        job = manager.submit_pipeline_job(
            title="Replay run",
            job_type="replay_run",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            commands=commands,
            resource_key=None,
        )
    except (ResourceBusyError, ConfigResolutionError) as exc:
        status = 409 if isinstance(exc, ResourceBusyError) else 400
        raise HTTPException(status_code=status, detail=str(exc))
    return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    html_path = settings.project_root / "vcbet" / "service" / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")
