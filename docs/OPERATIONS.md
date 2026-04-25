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
4. Run or check the daily analysis.
5. Review suggested picks and carteira impact in Carteira.
6. Update results and settlement when matches are complete.
7. Inspect jobs, logs, and errors in Monitor.

## Operational Data

- Daily analysis outputs are written under `data/runs/`.
- Replay outputs are written under `data/replays/`.
- Ledger/history files live under `data/history/`.
- Results and overrides live under `data/results/`.
- Service jobs and logs live under `data/service/jobs/` and `data/service/logs/`.

Do not delete, move, or bulk-clean runtime data during normal development.

## Commit Guidance

Usually commit source code, configs, tests, and documentation.

Be careful with runtime data. `data/runs/`, `data/replays/`, service jobs, and service logs are generated outputs. `data/history/` and `data/results/` can contain operational state and should only be committed intentionally.
