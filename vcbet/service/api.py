from __future__ import annotations

from datetime import datetime
import csv
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from vcbet.core.strategy_config import ConfigResolutionError, list_available_configs
from .commands import (
    build_analysis_command,
    build_closing_odds_command,
    build_daily_commands,
    build_replay_command,
    build_results_command,
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
    SettlementRequest,
)
from .settings import ServiceSettings

settings = ServiceSettings.load()
store = JobStore(settings.jobs_dir)
store.mark_interrupted_runs()
manager = JobManager(store, settings.logs_dir)

app = FastAPI(title="VCBet Service", version="0.5.0")


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
        "confidence_score": num("confidence_score"),
        "stake_units": num("stake_units"),
        "final_bet_status": pick("final_bet_status", "status"),
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


def _alias_candidate_files() -> list[Path]:
    candidates: list[Path] = []
    for base in [settings.project_root / "data" / "runs", settings.project_root / "data" / "replays"]:
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


def _alias_file_payload(path: Path, include_blocked: bool = True, cleanup_empty: bool = True) -> dict[str, object] | None:
    rows, delimiter, fieldnames = _read_text_csv(path)
    if not rows:
        if cleanup_empty and path.exists():
            path.unlink()
        return None

    normalized = _normalize_alias_rows(rows)
    visible = [
        row for row in normalized
        if row.get("match_status") == "pending_review" or (include_blocked and row.get("match_status") == "blocked")
    ]
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
        "items": visible,
        "total": len(visible),
    }


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
        rows = _read_csv_rows(ledger_file, limit=limit)
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
def list_alias_files(include_blocked: bool = True):
    items = []
    for file_path in _alias_candidate_files():
        payload = _alias_file_payload(file_path, include_blocked=include_blocked, cleanup_empty=True)
        if not payload:
            continue
        items.append({
            "pending_file": payload["pending_file"],
            "status_counts": payload["status_counts"],
            "total": payload["total"],
        })
    items.sort(key=lambda item: item["pending_file"], reverse=True)
    return {"items": items}


@app.get("/aliases/review")
def get_alias_review(pending_file: str, alias_file: str = "alias_times.json", include_blocked: bool = True):
    pending_path = _resolve_project_path(pending_file)
    payload = _alias_file_payload(pending_path, include_blocked=include_blocked, cleanup_empty=False)
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
        job = manager.submit_command_job(
            title=f"Gerar picks {req.mode}",
            job_type="analysis",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            command=command,
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


@app.post("/jobs/daily-run", response_model=JobCreatedResponse)
def start_daily_run(req: DailyRunRequest) -> JobCreatedResponse:
    try:
        commands = build_daily_commands(settings.project_root, req)
        if not commands:
            raise HTTPException(status_code=400, detail="daily-run sem passos habilitados")
        job = manager.submit_pipeline_job(
            title="Daily run",
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
        job = manager.submit_command_job(
            title="Replay run",
            job_type="replay_run",
            request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
            command=command,
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
