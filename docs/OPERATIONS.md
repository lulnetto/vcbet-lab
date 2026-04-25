# Operations

VCBet is operated as a local WSL/Linux project with the `ubet` conda environment.

## Environment

Preferred command style:

```bash
/home/otten/miniforge3/bin/conda run -n ubet <command>
```

From the project root:

```bash
cd /mnt/c/Users/Netto/Documents/VCBet
```

## Validate A Release

Run:

```bash
bash scripts/validate_release.sh
```

This executes focused regression tests, operational entrypoint smoke checks, JSON config loading, and service import checks.

## Start The Service

Discoverable service command:

```bash
/home/otten/miniforge3/bin/conda run -n ubet python run_service.py
```

The service defaults to `127.0.0.1:8010`. Host and port can be overridden with `VCBET_SERVICE_HOST` and `VCBET_SERVICE_PORT`.

`run_service.sh` and `scripts/run_service.sh` also exist, but they call `python3 run_service.py`; verify the active Python environment before using them.

## UI Screens

- Hoje: operational cockpit for the current day, next action, pipeline status, warnings, picks summary, and recent jobs.
- Carteira: ledger, picks, filters, KPIs, portfolio/performance views, and recent entries.
- Replay Lab: replay configuration, replay execution, and config comparison review.
- Qualidade de Dados: team aliases, pending reviews, blocked matches, and data-quality issues.
- Monitor: jobs, logs, errors, and service observability.

## Daily Flow

1. Open Hoje.
2. Check the next action and current pipeline status.
3. Resolve data-quality issues in Qualidade de Dados if any are blocking confidence.
4. Run or check `Gerar/Atualizar análise do dia`.
5. Review suggested picks and carteira impact in Carteira.
6. Use `Atualizar resultados e liquidar` when matches are complete.
7. Inspect jobs, logs, and errors in Monitor.

Normal operation should use the UI selectors for date, config, ledger, run, and replay. Manual paths remain available under `Avançado` for recovery cases, old artifacts, or data that has not been cataloged yet.

Operator actions are intentionally composed: `Atualizar resultados e liquidar` records separate results and settlement phases, and `Ciclo diário completo` records analysis, results, settlement, and catalog refresh phases. The Monitor remains the audit trail for substep success/failure.

Closing odds are maintenance data, not the original decision odds. The original `odd_entrada` remains immutable; automated/manual closing updates write only dedicated closing fields such as `closing_odd`, `closing_snapshot_time`, `closing_source`, and update status/error fields. The closing watcher/tick is disabled unless explicitly invoked, and `event_url` is optional but recommended for reliable collection.

Closing odds are not part of the default daily cycle. Use the watcher/manual maintenance tick only when closing capture is intentionally being run.

## Operational Data

- Daily analysis outputs are written under `data/runs/`.
- Replay outputs are written under `data/replays/`.
- Ledger/history files live under `data/history/`.
- Results and overrides live under `data/results/`.
- Service jobs and logs live under `data/service/jobs/` and `data/service/logs/`.
- Run and replay selectors read generated local catalogs at `data/runs/catalog.jsonl` and `data/replays/catalog.jsonl` when available.
- The official ledger is protected by a ledger-level portfolio gate before new official picks are appended. Cross-run/cross-config duplicate, correlated, or contradictory open exposures are blocked into a traceable review artifact instead of entering the official ledger silently.

Do not delete, move, or bulk-clean runtime data during normal development.

## Commit Guidance

Usually commit source code, configs, tests, and documentation.

Be careful with runtime data. `data/runs/`, `data/replays/`, service jobs, and service logs are generated outputs. `data/history/` and `data/results/` can contain operational state and should only be committed intentionally.
