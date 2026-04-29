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
from .routes import RouteContext, register_all_routes
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


route_context = RouteContext(
    settings=settings,
    manager=manager,
    resource_key=_resource_key,
    resolve_project_path=_resolve_project_path,
    read_text_csv=_read_text_csv,
    write_text_csv=_write_text_csv,
    read_csv_rows=_read_csv_rows,
    read_ledger_rows=_read_ledger_rows,
    compact_pick_row=_compact_pick_row,
    alias_candidate_files=_alias_candidate_files,
    normalize_alias_rows=_normalize_alias_rows,
    registry_approved_keys=_registry_approved_keys,
    alias_file_payload=_alias_file_payload,
    project_rel=_project_rel,
    read_jsonl_catalog=_read_jsonl_catalog,
    refresh_catalog_if_needed=_refresh_catalog_if_needed,
    run_label=_run_label,
    replay_label=_replay_label,
    active_catalog_items=_active_catalog_items,
    safe_limit=_safe_limit,
)
register_all_routes(app, route_context)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    html_path = settings.project_root / "vcbet" / "service" / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")
