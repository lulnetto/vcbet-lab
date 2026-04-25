# Pipeline Daily Run Context Pack

## Purpose

Work on the daily run path that collects snapshots, normalizes odds, matches teams, prices candidates, applies decision policy, writes run artifacts, and appends accepted picks.

## Include by Default

- `vcbet/core/pipeline_ev.py` as the compatibility entrypoint for `processar_pipeline`
- `vcbet/core/pipeline/input_loader.py`
- `vcbet/core/pipeline/team_resolution.py`
- `vcbet/core/pipeline/pricing_stage.py`
- `vcbet/core/pipeline/filtering_stage.py`
- `vcbet/core/pipeline/output_writer.py`
- `vcbet/core/pipeline/quality_report.py`
- `run_project.sh`
- `vcbet/core/run_utils.py`
- `vcbet/core/strategy_config.py`
- `vcbet/collectors/odds_collector.py`
- `vcbet/collectors/footystats_xg_collector.py`
- `vcbet/core/market_normalizer.py`
- `vcbet/core/team_matcher.py`
- `vcbet/core/pick_features.py`
- `vcbet/core/decision_policy.py`
- `vcbet/core/line_selector.py`
- `vcbet/core/ledger_manager.py`
- `tests/test_daily_config_selection.py`
- `tests/test_temporal_contract.py`

## Include Only If Needed

- `run_service.py` when the service startup path is part of the task.
- `vcbet/service/commands.py` when service-triggered daily runs change.
- `vcbet/service/job_runner.py` when job execution behavior changes.
- `scripts/run_project.sh` if the script copy is the edited entrypoint.
- `vcbet/core/pricing_engine.py` when pricing formulas are involved.
- `vcbet/core/ledger_portfolio_gate.py` when official ledger exposure blocks appends.
- `configs/legacy_v2.json`, `configs/champion_strict.json`, or `configs/intermediate_balanced.json` for config-specific runs.
- One run manifest or tiny artifact sample only under the exception rules in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/runs/**` by default
- `data/history/**` by default
- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated replays and results
- full ledgers

## Key Invariants

- The daily run must preserve target date, run ID, config name, config fingerprint, snapshot provenance, and temporal contract fields.
- Odds and xG snapshots must be resolved explicitly and recorded in manifests.
- Accepted picks must pass pricing, risk, selection, and ledger append gates in the expected order.
- `vcbet/core/pipeline_ev.py` remains the stable public entrypoint; `vcbet/core/pipeline/*.py` stage modules are implementation details from the mechanical split.
- The pipeline stage split was intended to leave pricing, filtering, EV, ledger append, quality report, and output semantics unchanged.
- Orchestration should remain thin; domain behavior belongs in domain modules and application use cases.

## Validation Commands

- `python3 -m pytest tests/test_daily_config_selection.py tests/test_temporal_contract.py`
- Add `tests/test_decision_architecture.py tests/test_pricing_outputs.py tests/test_ledger_portfolio_gate.py` when the changed path crosses selection, pricing output, or ledger append behavior.

## Known Hotspots

- `vcbet/core/pipeline_ev.py` was mechanically reduced to a thin orchestrator/compatibility layer for the daily run.
- `vcbet/core/pipeline/*.py` stage modules now hold loading, team resolution, pricing, filtering, output writing, and quality-report implementation details.
- `run_project.sh` and `scripts/run_project.sh` are orchestration entrypoints that should stay thin.

## Refactor Direction

Move the daily run into an application use case with explicit input snapshots and output writers. Keep collectors as adapters, domain modules pure, and ledger writes behind a repository contract.
