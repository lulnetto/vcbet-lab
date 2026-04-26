# Service API Context Pack

## Purpose

Work on FastAPI routes, schemas, service commands, job orchestration, dashboard payloads, catalogs, and API contracts consumed by the static frontend.

## Include by Default

- `vcbet/service/api.py`
- `vcbet/service/routes/*.py`
- `vcbet/service/commands.py`
- `vcbet/service/job_runner.py`
- `vcbet/service/job_store.py`
- `vcbet/service/dashboard.py`
- `vcbet/service/schemas.py`
- `vcbet/service/settings.py`
- `vcbet/service/team_registry_api.py`
- `tests/test_service_composed_workflows.py`
- `tests/test_daily_config_selection.py`
- `tests/test_team_registry_api.py`

## Include Only If Needed

- `vcbet/service/static/js/api.js` and `vcbet/service/static/js/screens.js` when route response shape changes.
- `vcbet/core/ledger_manager.py` when ledger rows or dashboard filters change.
- `vcbet/replay/replay_pipeline.py` when replay summary routes change.
- `vcbet/core/pipeline_ev.py` only for daily-run command effects through the compatibility entrypoint.
- `vcbet/core/pipeline/input_loader.py`, `vcbet/core/pipeline/pricing_stage.py`, `vcbet/core/pipeline/filtering_stage.py`, `vcbet/core/pipeline/output_writer.py`, and `vcbet/core/pipeline/quality_report.py` only when service behavior depends on daily pipeline stage internals.
- `scripts/build_run_catalog.py` or `scripts/build_replay_catalog.py` when catalog refresh behavior changes.
- One job JSON or log excerpt only under the service job/log exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/service/**` by default
- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results
- full ledgers

## Key Invariants

- API response shapes consumed by the frontend must remain backward compatible unless the frontend changes in the same task.
- Job commands must remain explicit, auditable, and cancellable through `JobManager`.
- `JobStore` writes job JSON atomically with a temp file, fsync where feasible, and replace. Preserve the existing job payload shape unless a migration is intentional.
- Service code should not expand direct script coupling; current script calls should be treated as refactor debt.
- Service jobs that touch the canonical ledger must respect `vcbet/ledger/repository.py` transactional ledger helpers. Scheduler or route-triggered work must not bypass ledger locking.
- Dashboard payloads must preserve filter semantics, settled/open counts, recent entries, CLV fields, and breakdown shapes.
- Active job persistence exists. Broader service robustness and APScheduler lifecycle work are Phase 3 items and are not implemented yet.

## Validation Commands

- `python3 -m pytest tests/test_service_composed_workflows.py tests/test_daily_config_selection.py tests/test_team_registry_api.py`
- Add `tests/test_closing_watcher.py` when closing watcher routes or commands are affected.

## Known Hotspots

- `vcbet/service/api.py` is now composed with route modules under `vcbet/service/routes/`.
- Route modules should stay thin over command builders, dashboard/read-model helpers, and job orchestration.
- `vcbet/service/team_registry_api.py` is over 300 LOC and currently bridges service and script-level alias sync.
- `vcbet/service/dashboard.py` is over 300 LOC and exposes pandas-shaped ledger logic to service payloads.

## Refactor Direction

Split route handlers from application use cases and read models. Keep FastAPI thin over service/application functions, and move CSV/job/catalog details behind repositories or command builders.
