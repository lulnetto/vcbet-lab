# Project Map

This map explains what each major area is for and whether it is usually source code, compatibility glue, or runtime output.

## Main Package: `vcbet/`

### `vcbet/core/`

Purpose: core valuation and decision logic, including pricing, market normalization, pick filters, portfolio/risk rules, team matching, strategy config, temporal contracts, and the daily pipeline.

Type: source code.

Edit here: yes, for valuation behavior and core domain changes.

### `vcbet/collectors/`

Purpose: data collection modules for odds, xG, closing odds, and match results.

Type: source code.

Edit here: yes, when changing collection behavior or source integrations.

### `vcbet/replay/`

Purpose: historical replay and config comparison pipeline.

Type: source code.

Edit here: yes, for replay behavior, comparison outputs, or calibration workflows.

### `vcbet/service/`

Purpose: HTTP service, API schemas, command building, dashboard aggregation, job execution, and job storage.

Type: source code.

Edit here: yes, for API/service behavior. Preserve API contracts unless the change intentionally includes a migration.

Files currently present:

- `vcbet/service/api.py`: FastAPI app and routes.
- `vcbet/service/dashboard.py`: dashboard/cockpit data aggregation.
- `vcbet/service/job_runner.py`: background job execution.
- `vcbet/service/commands.py`: operational command construction.
- `vcbet/service/job_store.py`: service job metadata persistence.
- `vcbet/service/schemas.py`: request/response schemas.
- `vcbet/service/settings.py`: service paths, host, and port settings.

### `vcbet/settlement/`

Purpose: post-match settlement and ledger reporting.

Type: source code.

Edit here: yes, for result settlement and reporting logic.

### `vcbet/paths.py`

Purpose: shared project path constants.

Type: source code.

Edit here: rarely, only when path conventions change.

## Frontend: `vcbet/service/static/`

Purpose: static browser UI served by the service.

Type: source code.

Edit here: yes, for UI work. See [FRONTEND_MAP.md](FRONTEND_MAP.md).

## Service/API Entrypoints

- `run_service.py`: root service startup entrypoint using Uvicorn.
- `run_service.sh`: shell wrapper around `python3 run_service.py`.
- `scripts/run_service.py`: duplicate service startup wrapper.
- `scripts/run_service.sh`: shell wrapper around `python3 run_service.py`.

Type: source code / operational entrypoints.

Edit here: rarely. Prefer changing `vcbet/service/` for service behavior.

## Compatibility / Legacy Entrypoints

Several root-level Python files are thin wrappers that call modules in `vcbet.*` with `runpy.run_module`. Examples currently include:

- `config_ligas.py`
- `correlation_rules.py`
- `footystats_xg_collector.py`
- `ledger_manager.py`
- `market_normalizer.py`
- `market_thresholds.py`
- `odds_collector.py`
- `pick_filter.py`
- `pricing_engine.py`
- `report_ledger.py`
- `run_utils.py`
- `team_matcher.py`

Purpose: compatibility / legacy entrypoints after the package refactor.

Type: compatibility source code.

Edit here: usually no. Prefer editing the matching module under `vcbet/`.

## Runtime And Data

- `data/runs/`: generated daily run folders and run manifests.
- `data/replays/`: generated replay and comparison runs.
- `data/history/`: ledger/history files used by operations.
- `data/results/`: collected and overridden match results.
- `data/service/jobs/`: service job metadata.
- `data/service/logs/`: service job logs.

Type: runtime artifacts and operational data.

Edit here: usually no during code changes. Do not clean, move, or delete data as part of routine development. Some history/results files may be intentional project inputs.

## Configs

- `configs/`: versioned strategy presets.
- `ligas.json`: league configuration.
- `alias_times.json`: team alias mapping.

Type: project configuration/input.

Edit here: yes, only when intentionally changing strategy, league, or alias behavior.

## Scripts

- `scripts/validate_release.sh`: minimal release validation gate.
- `scripts/approve_alias_review.py`: approves pending aliases into `alias_times.json`.
- `scripts/dedupe_ledger.py`: ledger maintenance utility.
- `scripts/run_project.sh`: operational wrapper copy.
- `scripts/run_service.py` and `scripts/run_service.sh`: service wrappers.
- `run_project.sh`: main operational CLI wrapper for daily analysis modes.

Type: operational scripts.

Edit here: only when changing operational workflows or validation.

## Future Development Guidance

- Core betting/valuation changes should happen under `vcbet/core/`.
- Collection changes should happen under `vcbet/collectors/`.
- API and job changes should happen under `vcbet/service/`.
- UI changes should happen under `vcbet/service/static/`.
- Replay changes should happen under `vcbet/replay/`.
- Settlement changes should happen under `vcbet/settlement/`.
- Avoid adding new behavior to root compatibility wrappers unless the goal is explicitly compatibility.
