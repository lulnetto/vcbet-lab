from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schemas import (
    AnalysisRequest,
    ClosingOddsRequest,
    DailyRunRequest,
    ReconcileUnmatchedRequest,
    ReplayRunRequest,
    ResultsCollectionRequest,
    ResultsSettlementRequest,
    SettlementRequest,
)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    command: list[str]
    cwd: Path


def _resolve(project_root: Path, value: str | None) -> str | None:
    if value is None:
        return None
    path = Path(value)
    return str(path if path.is_absolute() else (project_root / path))


def _append_if(args: list[str], condition: bool, flag: str) -> None:
    if condition:
        args.append(flag)


def build_analysis_command(project_root: Path, req: AnalysisRequest) -> CommandSpec:
    script = project_root / "run_project.sh"
    args = ["bash", str(script), "--mode", req.mode]
    if req.date:
        args += ["--date", req.date]
    if req.run_id:
        args += ["--run-id", req.run_id]
    if req.odds_file:
        args += ["--odds-file", _resolve(project_root, req.odds_file)]
    if req.xg_file:
        args += ["--xg-file", _resolve(project_root, req.xg_file)]
    args += [
        "--ledger-file", _resolve(project_root, req.ledger_file),
        "--output-dir", _resolve(project_root, req.output_dir),
        "--python-bin", req.python_bin,
    ]
    if req.config_file:
        args += ["--config-file", _resolve(project_root, req.config_file)]
    elif req.config_name:
        args += ["--config-name", req.config_name]
    _append_if(args, req.json_output, "--json")
    _append_if(args, req.debug, "--debug")
    _append_if(args, req.dry_run, "--dry-run")
    args += ["--xg-source", req.xg_source]
    return CommandSpec(name="analysis", command=args, cwd=project_root)


def build_closing_odds_command(project_root: Path, req: ClosingOddsRequest) -> CommandSpec:
    script = project_root / "scripts" / "update_closing_odds.py"
    args = [
        req.python_bin,
        str(script),
        "--ledger-file", _resolve(project_root, req.ledger_file),
        "--window-minutes", str(req.window_minutes),
        "--allow-past-minutes", str(req.allow_past_minutes),
    ]
    _append_if(args, req.all_pending, "--all-pending")
    for bet_id in req.bet_ids:
        args += ["--bet-id", bet_id]
    return CommandSpec(name="closing_odds", command=args, cwd=project_root)


def build_results_command(project_root: Path, req: ResultsCollectionRequest) -> CommandSpec:
    args = [
        req.python_bin,
        "-m",
        "vcbet.collectors.results_collector",
        "--ledger-file", _resolve(project_root, req.ledger_file),
        "--output-file", _resolve(project_root, req.output_file),
        "--grace-minutes", str(req.grace_minutes),
        "--debug-dir", _resolve(project_root, req.debug_dir),
        "--max-pages", str(req.max_pages),
    ]
    _append_if(args, req.all_pending, "--all-pending")
    _append_if(args, req.debug, "--debug")
    if req.source:
        args += ["--source", req.source]
    return CommandSpec(name="results_collection", command=args, cwd=project_root)


def build_settlement_command(project_root: Path, req: SettlementRequest) -> CommandSpec:
    args = [
        req.python_bin,
        "-m",
        "vcbet.settlement.settlement_engine",
        "--ledger-file", _resolve(project_root, req.ledger_file),
        "--results-file", _resolve(project_root, req.results_file),
    ]
    if req.overrides_file:
        args += ["--overrides-file", _resolve(project_root, req.overrides_file)]
    _append_if(args, req.no_overrides, "--no-overrides")
    return CommandSpec(name="settlement", command=args, cwd=project_root)


def build_run_catalog_command(project_root: Path) -> CommandSpec:
    return CommandSpec(
        name="refresh_run_catalog",
        command=["python3", str(project_root / "scripts" / "build_run_catalog.py")],
        cwd=project_root,
    )


def build_replay_catalog_command(project_root: Path) -> CommandSpec:
    return CommandSpec(
        name="refresh_replay_catalog",
        command=["python3", str(project_root / "scripts" / "build_replay_catalog.py")],
        cwd=project_root,
    )


def build_results_settlement_commands(project_root: Path, req: ResultsSettlementRequest) -> list[CommandSpec]:
    return [
        build_results_command(
            project_root,
            ResultsCollectionRequest(
                ledger_file=req.ledger_file,
                output_file=req.results_file,
                all_pending=req.all_pending,
                grace_minutes=req.results_grace_minutes,
                debug=req.results_debug,
                max_pages=req.results_max_pages,
                source=req.results_source,
                python_bin=req.python_bin,
            ),
        ),
        build_settlement_command(
            project_root,
            SettlementRequest(
                ledger_file=req.ledger_file,
                results_file=req.results_file,
                overrides_file=req.overrides_file,
                no_overrides=req.no_overrides,
                python_bin=req.python_bin,
            ),
        ),
    ]


def build_reconcile_unmatched_command(project_root: Path, req: ReconcileUnmatchedRequest) -> CommandSpec:
    script = project_root / "scripts" / "retry_unmatched_settlement.py"
    args = [
        req.python_bin,
        str(script),
        "--ledger-file", _resolve(project_root, req.ledger_file),
        "--results-file", _resolve(project_root, req.results_file),
        "--max-pages", str(req.max_pages),
    ]
    if req.date:
        args += ["--date", req.date]
    if req.source:
        args += ["--source", req.source]
    if req.overrides_file:
        args += ["--overrides-file", _resolve(project_root, req.overrides_file)]
    _append_if(args, req.debug, "--debug")
    _append_if(args, req.dry_run, "--dry-run")
    _append_if(args, req.no_overrides, "--no-overrides")
    return CommandSpec(name="reconcile_unmatched", command=args, cwd=project_root)


def build_daily_commands(project_root: Path, req: DailyRunRequest) -> list[CommandSpec]:
    commands: list[CommandSpec] = []
    added_analysis = False

    if not req.skip_analysis:
        commands.append(
            build_analysis_command(
                project_root,
                AnalysisRequest(
                    mode="full",
                    date=req.date,
                    run_id=req.run_id,
                    ledger_file=req.ledger_file,
                    output_dir=req.output_dir,
                    python_bin=req.python_bin,
                    json_output=req.json_output,
                    debug=req.debug,
                    dry_run=req.dry_run,
                    config_file=req.config_file,
                    config_name=req.config_name,
                    xg_source=req.xg_source,
                ),
            )
        )
        commands.append(build_run_catalog_command(project_root))
        added_analysis = True

    if not req.skip_closing_odds:
        commands.append(
            build_closing_odds_command(
                project_root,
                ClosingOddsRequest(
                    ledger_file=req.ledger_file,
                    window_minutes=req.closing_window_minutes,
                    allow_past_minutes=req.closing_allow_past_minutes,
                    all_pending=False,
                    python_bin=req.python_bin,
                ),
            )
        )

    if not req.skip_results_collection:
        commands.append(
            build_results_command(
                project_root,
                ResultsCollectionRequest(
                    ledger_file=req.ledger_file,
                    output_file=req.results_file,
                    grace_minutes=req.results_grace_minutes,
                    debug=req.debug,
                    max_pages=req.results_max_pages,
                    source=req.results_source,
                    python_bin=req.python_bin,
                ),
            )
        )

    if not req.skip_settlement:
        commands.append(
            build_settlement_command(
                project_root,
                SettlementRequest(
                    ledger_file=req.ledger_file,
                    results_file=req.results_file,
                    overrides_file=req.overrides_file,
                    python_bin=req.python_bin,
                ),
            )
        )

    if req.refresh_catalogs:
        if not added_analysis:
            commands.append(build_run_catalog_command(project_root))
        commands.append(build_replay_catalog_command(project_root))

    return commands


def build_replay_command(project_root: Path, req: ReplayRunRequest) -> CommandSpec:
    import tempfile
    if req.persist:
        output_dir = _resolve(project_root, req.output_dir)
    else:
        output_dir = tempfile.mkdtemp(prefix="vcbet_replay_")
    args = [
        req.python_bin,
        "-m",
        "vcbet.replay.replay_pipeline",
        "--source-run-dir", _resolve(project_root, req.source_run_dir),
        "--output-dir", output_dir,
        "--python-bin", req.python_bin,
    ]
    for config_name in req.configs:
        args += ["--config", config_name]
    _append_if(args, getattr(req, "evaluate_results", False), "--evaluate-results")
    if getattr(req, "results_source", None):
        args += ["--results-source", req.results_source]
    args += ["--results-grace-minutes", str(getattr(req, "results_grace_minutes", 110))]
    args += ["--results-max-pages", str(getattr(req, "results_max_pages", 6))]
    _append_if(args, getattr(req, "results_debug", False), "--results-debug")
    return CommandSpec(name="replay_run", command=args, cwd=project_root)
