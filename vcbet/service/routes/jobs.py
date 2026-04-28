from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from vcbet.core.strategy_config import ConfigResolutionError
from vcbet.service.commands import (
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
from vcbet.service.job_runner import ResourceBusyError
from vcbet.service.schemas import (
    AnalysisRequest,
    ClosingOddsRequest,
    DailyRunRequest,
    JobCreatedResponse,
    JobListResponse,
    ReplayRunRequest,
    ResultsCollectionRequest,
    ResultsSettlementRequest,
    SettlementRequest,
)

from . import RouteContext


def register_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get("/jobs", response_model=JobListResponse)
    def list_jobs(limit: int = 50) -> JobListResponse:
        items = ctx.manager.list_jobs()[:limit]
        return JobListResponse(items=items)

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str):
        job = ctx.manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job não encontrado")
        return job

    @app.get("/jobs/{job_id}/logs", response_class=PlainTextResponse)
    def get_job_logs(job_id: str, lines: int = 200) -> str:
        job = ctx.manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job não encontrado")
        return ctx.manager.read_log_tail(job_id, lines=lines)

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        job = ctx.manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job não encontrado")
        if not ctx.manager.cancel_job(job_id):
            return {"job_id": job_id, "cancelled": False, "message": "job não está rodando"}
        return {"job_id": job_id, "cancelled": True}

    @app.delete("/jobs/{job_id}")
    def delete_job(job_id: str):
        job = ctx.manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job não encontrado")
        if job.status in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="Não é permitido deletar job em execução. Cancele primeiro.")
        ctx.manager.store.delete(job_id)
        return {"job_id": job_id, "deleted": True}

    @app.post("/jobs/cleanup-failed")
    def cleanup_failed_jobs():
        removed = ctx.manager.store.delete_finished_failed()
        return {"removed": removed}

    @app.post("/jobs/analysis", response_model=JobCreatedResponse)
    def start_analysis(req: AnalysisRequest) -> JobCreatedResponse:
        try:
            command = build_analysis_command(ctx.settings.project_root, req)
            commands = [command, build_run_catalog_command(ctx.settings.project_root)]
            job = ctx.manager.submit_pipeline_job(
                title="Análise do dia",
                job_type="analysis",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                commands=commands,
                resource_key=ctx.resource_key(ctx.settings.project_root, req.ledger_file),
            )
        except (ResourceBusyError, ConfigResolutionError) as exc:
            status = 409 if isinstance(exc, ResourceBusyError) else 400
            raise HTTPException(status_code=status, detail=str(exc))
        return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)

    @app.post("/jobs/closing-odds", response_model=JobCreatedResponse)
    def start_closing_odds(req: ClosingOddsRequest) -> JobCreatedResponse:
        command = build_closing_odds_command(ctx.settings.project_root, req)
        try:
            job = ctx.manager.submit_command_job(
                title="Atualizar closing odds",
                job_type="closing_odds",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                command=command,
                resource_key=ctx.resource_key(ctx.settings.project_root, req.ledger_file),
            )
        except ResourceBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)

    @app.post("/jobs/results-collection", response_model=JobCreatedResponse)
    def start_results_collection(req: ResultsCollectionRequest) -> JobCreatedResponse:
        command = build_results_command(ctx.settings.project_root, req)
        try:
            job = ctx.manager.submit_command_job(
                title="Atualizar resultados",
                job_type="results_collection",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                command=command,
                resource_key=ctx.resource_key(ctx.settings.project_root, req.ledger_file),
            )
        except ResourceBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)

    @app.post("/jobs/settlement", response_model=JobCreatedResponse)
    def start_settlement(req: SettlementRequest) -> JobCreatedResponse:
        command = build_settlement_command(ctx.settings.project_root, req)
        try:
            job = ctx.manager.submit_command_job(
                title="Liquidar ledger",
                job_type="settlement",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                command=command,
                resource_key=ctx.resource_key(ctx.settings.project_root, req.ledger_file),
            )
        except ResourceBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)

    @app.post("/jobs/results-settlement-cycle", response_model=JobCreatedResponse)
    def start_results_settlement_cycle(req: ResultsSettlementRequest) -> JobCreatedResponse:
        commands = build_results_settlement_commands(ctx.settings.project_root, req)
        try:
            job = ctx.manager.submit_pipeline_job(
                title="Resultados + settlement",
                job_type="results_settlement_cycle",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                commands=commands,
                resource_key=ctx.resource_key(ctx.settings.project_root, req.ledger_file),
            )
        except ResourceBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)

    @app.post("/jobs/daily-run", response_model=JobCreatedResponse)
    def start_daily_run(req: DailyRunRequest) -> JobCreatedResponse:
        try:
            commands = build_daily_commands(ctx.settings.project_root, req)
            if not commands:
                raise HTTPException(status_code=400, detail="daily-run sem passos habilitados")
            job = ctx.manager.submit_pipeline_job(
                title="Ciclo diário completo",
                job_type="daily_run",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                commands=commands,
                resource_key=ctx.resource_key(ctx.settings.project_root, req.ledger_file),
            )
        except (ResourceBusyError, ConfigResolutionError) as exc:
            status = 409 if isinstance(exc, ResourceBusyError) else 400
            raise HTTPException(status_code=status, detail=str(exc))
        return JobCreatedResponse(job_id=job.id, status=job.status, title=job.title)

    @app.post("/jobs/replay-run", response_model=JobCreatedResponse)
    def start_replay_run(req: ReplayRunRequest) -> JobCreatedResponse:
        try:
            command = build_replay_command(ctx.settings.project_root, req)
            commands = [command]
            if req.persist:
                commands.append(build_replay_catalog_command(ctx.settings.project_root))
            job = ctx.manager.submit_pipeline_job(
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
