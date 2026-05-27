from __future__ import annotations

import csv
from datetime import datetime
import io
from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response

from vcbet.core.candidate_audit import AUDIT_COLS, write_candidate_audit_summary_for_group
from vcbet.core.strategy_config import ConfigResolutionError, resolve_config_file
from vcbet.service.commands import (
    build_analysis_batch_commands,
    build_analysis_command,
    build_closing_odds_command,
    build_daily_commands,
    build_reconcile_unmatched_command,
    build_replay_command,
    build_replay_catalog_command,
    build_run_catalog_command,
    build_results_command,
    build_results_settlement_commands,
    build_settlement_command,
)
from vcbet.service.job_runner import ResourceBusyError
from vcbet.service.schemas import (
    AnalysisBatchCreatedItem,
    AnalysisBatchCreatedResponse,
    AnalysisBatchRequest,
    AnalysisRequest,
    ClosingOddsRequest,
    DailyRunRequest,
    JobCreatedResponse,
    JobListResponse,
    ReconcileUnmatchedRequest,
    ReplayRunRequest,
    ResultsCollectionRequest,
    ResultsSettlementRequest,
    SettlementRequest,
)

from . import RouteContext


def _request_payload(req) -> dict:
    return req.model_dump() if hasattr(req, "model_dump") else req.dict()


def _new_run_group_id() -> str:
    return f"run_group_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _resolve_ledger_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (project_root / path).resolve()


def _job_output_dir(ctx: RouteContext, job) -> Path:
    output_dir = str((job.request or {}).get("output_dir") or "data/runs")
    return ctx.resolve_project_path(output_dir)


def _job_timestamp(value) -> float | None:
    if value is None:
        return None
    try:
        return value.timestamp()
    except AttributeError:
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except ValueError:
            return None


def _candidate_audit_files_for_job(ctx: RouteContext, job) -> list[Path]:
    req = job.request or {}
    output_dir = _job_output_dir(ctx, job)
    if job.job_type == "analysis_batch":
        run_group_id = str(req.get("run_group_id") or "").strip()
        run_date = str(req.get("run_date") or "").strip()
        if not run_group_id:
            return []
        root = output_dir / run_date if run_date else output_dir
        if not root.exists():
            return []
        return sorted(
            path
            for path in root.glob(f"{run_group_id}_*/candidate_audit.csv")
            if not path.parent.name.endswith("_source")
        )

    run_id = str(req.get("run_id") or "").strip()
    run_date = str(req.get("date") or req.get("run_date") or "").strip()
    candidates: list[Path] = []
    if run_id:
        if run_date:
            candidates.append(output_dir / run_date / run_id / "candidate_audit.csv")
        candidates.extend(output_dir.glob(f"*/{run_id}/candidate_audit.csv"))
        return sorted({path for path in candidates if path.exists()})

    root = output_dir / run_date if run_date else output_dir
    if not root.exists():
        return []
    created_at = _job_timestamp(job.created_at)
    finished_at = _job_timestamp(job.finished_at) or datetime.now().timestamp()
    dated_candidates = []
    for path in root.glob("*/candidate_audit.csv"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if created_at is None or (created_at - 60 <= mtime <= finished_at + 300):
            dated_candidates.append(path)
    dated_candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dated_candidates[:1]


def _csv_download_response(filename: str, rows: list[dict[str, str]], fieldnames: list[str]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, delimiter=";")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _read_audit_rows(ctx: RouteContext, paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        file_rows, _, _ = ctx.read_text_csv(path)
        rows.extend(file_rows)
    return rows


def _validate_analysis_batch(ctx: RouteContext, req: AnalysisBatchRequest) -> list[Path]:
    try:
        datetime.strptime(str(req.run_date or ""), "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_date deve estar no formato YYYY-MM-DD.") from exc
    if not req.items:
        raise HTTPException(status_code=400, detail="items não pode ser vazio.")

    config_names: list[str] = []
    ledger_paths: list[Path] = []
    for index, item in enumerate(req.items):
        config_name = str(item.config_name or "").strip()
        ledger_path = str(item.ledger_path or "").strip()
        if not config_name:
            raise HTTPException(status_code=400, detail=f"items[{index}].config_name é obrigatório.")
        if not ledger_path:
            raise HTTPException(status_code=400, detail=f"items[{index}].ledger_path é obrigatório.")
        try:
            resolve_config_file(config_name=config_name, strict=True)
        except ConfigResolutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        resolved_ledger = _resolve_ledger_path(ctx.settings.project_root, ledger_path)
        resolved_ledger.parent.mkdir(parents=True, exist_ok=True)
        config_names.append(config_name)
        ledger_paths.append(resolved_ledger)

    duplicate_configs = sorted({name for name in config_names if config_names.count(name) > 1})
    if duplicate_configs:
        raise HTTPException(status_code=400, detail=f"Configs duplicadas no batch: {', '.join(duplicate_configs)}")

    normalized_ledgers = [str(path) for path in ledger_paths]
    duplicate_ledgers = sorted({path for path in normalized_ledgers if normalized_ledgers.count(path) > 1})
    if duplicate_ledgers and not req.allow_shared_ledger:
        raise HTTPException(
            status_code=400,
            detail="Ledgers duplicados no batch: " + ", ".join(duplicate_ledgers) + ". Use allow_shared_ledger=true para permitir.",
        )
    return ledger_paths


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

    @app.get("/jobs/{job_id}/candidate-audit")
    def get_job_candidate_audit(job_id: str):
        job = ctx.manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job não encontrado")
        files = _candidate_audit_files_for_job(ctx, job)
        if not files:
            raise HTTPException(status_code=404, detail="candidate_audit.csv não encontrado para este job.")
        if len(files) == 1:
            return FileResponse(
                files[0],
                media_type="text/csv",
                filename=files[0].name,
            )
        rows = _read_audit_rows(ctx, files)
        run_group_id = str((job.request or {}).get("run_group_id") or job_id)
        return _csv_download_response(f"{run_group_id}_candidate_audit.csv", rows, AUDIT_COLS)

    @app.get("/jobs/{job_id}/candidate-audit-summary")
    def get_job_candidate_audit_summary(job_id: str):
        job = ctx.manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job não encontrado")
        req = job.request or {}
        if job.job_type != "analysis_batch":
            raise HTTPException(status_code=404, detail="Resumo de auditoria disponível para jobs batch.")
        run_group_id = str(req.get("run_group_id") or "").strip()
        run_date = str(req.get("run_date") or "").strip()
        if not run_group_id:
            raise HTTPException(status_code=404, detail="run_group_id ausente neste job.")
        output_dir = _job_output_dir(ctx, job)
        summary_file = output_dir / run_date / run_group_id / "candidate_audit_summary.csv"
        if not summary_file.exists():
            files = _candidate_audit_files_for_job(ctx, job)
            if not files:
                raise HTTPException(status_code=404, detail="Arquivos de auditoria não encontrados para gerar resumo.")
            summary_file = write_candidate_audit_summary_for_group(
                output_dir=output_dir,
                run_group_id=run_group_id,
                run_date=run_date or None,
                source_snapshot_id=str(req.get("source_snapshot_id") or ""),
            )
        return FileResponse(
            summary_file,
            media_type="text/csv",
            filename=summary_file.name,
        )

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

    @app.post("/jobs/analysis-batch", response_model=AnalysisBatchCreatedResponse)
    def start_analysis_batch(req: AnalysisBatchRequest) -> AnalysisBatchCreatedResponse:
        try:
            ledger_paths = _validate_analysis_batch(ctx, req)
            run_group_id = _new_run_group_id()
            source_snapshot_id = f"{run_group_id}_source"
            commands = build_analysis_batch_commands(
                ctx.settings.project_root,
                req,
                run_group_id=run_group_id,
                source_snapshot_id=source_snapshot_id,
            )
            request_payload = _request_payload(req)
            request_payload["run_group_id"] = run_group_id
            request_payload["source_snapshot_id"] = source_snapshot_id
            request_payload["resolved_ledger_paths"] = [str(path) for path in ledger_paths]
            job = ctx.manager.submit_pipeline_job(
                title="Executar múltiplos perfis",
                job_type="analysis_batch",
                request=request_payload,
                commands=commands,
                resource_key=f"analysis_batch:{run_group_id}",
            )
        except (ResourceBusyError, ConfigResolutionError) as exc:
            status = 409 if isinstance(exc, ResourceBusyError) else 400
            raise HTTPException(status_code=status, detail=str(exc))
        return AnalysisBatchCreatedResponse(
            job_id=job.id,
            status=job.status,
            title=job.title,
            run_group_id=run_group_id,
            source_snapshot_id=source_snapshot_id,
            items=[
                AnalysisBatchCreatedItem(config_name=item.config_name, ledger_path=item.ledger_path)
                for item in req.items
            ],
        )

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

    @app.post("/jobs/reconcile-unmatched", response_model=JobCreatedResponse)
    def start_reconcile_unmatched(req: ReconcileUnmatchedRequest) -> JobCreatedResponse:
        command = build_reconcile_unmatched_command(ctx.settings.project_root, req)
        try:
            job = ctx.manager.submit_command_job(
                title="Reprocessar unmatched",
                job_type="reconcile_unmatched",
                request=req.model_dump() if hasattr(req, "model_dump") else req.dict(),
                command=command,
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
