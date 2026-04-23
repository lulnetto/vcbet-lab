from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from strategy_config import ConfigResolutionError, list_available_configs
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

app = FastAPI(title="UBET Service", version="0.3.0")


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
            title=f"Análise {req.mode}",
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
            title="Closing odds",
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
            title="Coleta de resultados",
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
            title="Settlement",
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
    html_path = settings.project_root / "ubet_service" / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")
