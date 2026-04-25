# VCBet

VCBet is a personal football betting valuation and research system. It uses football data such as xG/xGA, odds snapshots, market normalization, risk rules, replay runs, and settlement outputs to identify possible value odds across markets such as asian total, total goals, team total, BTTS, and related markets.

VCBet is not a proven profitable betting engine. Treat it as a personal research and operational tool whose outputs still require review, data-quality checks, and bankroll discipline.

## Environment

Canonical environment:

- WSL/Linux
- project path: `/mnt/c/Users/Netto/Documents/VCBet`
- conda env: `ubet`
- preferred command style: `/home/otten/miniforge3/bin/conda run -n ubet <command>`

## Validate

Run the minimal release gate before continuing development:

```bash
bash scripts/validate_release.sh
```

## Run The Service

The service entrypoint is currently:

```bash
/home/otten/miniforge3/bin/conda run -n ubet python run_service.py
```

`run_service.py` loads `vcbet.service.api:app` with Uvicorn. Defaults are `127.0.0.1:8010`, configurable through `VCBET_SERVICE_HOST` and `VCBET_SERVICE_PORT`.

## Where Things Live

- Frontend: `vcbet/service/static/`
- Service/API: `vcbet/service/`
- Core valuation modules: `vcbet/core/`
- Collectors: `vcbet/collectors/`
- Replay: `vcbet/replay/`
- Settlement: `vcbet/settlement/`
- Strategy configs: `configs/`
- Runtime data and generated outputs: `data/`
- Operational scripts: `run_project.sh` and `scripts/`

## Documentation

- [Project map](docs/PROJECT_MAP.md)
- [Operations](docs/OPERATIONS.md)
- [Frontend map](docs/FRONTEND_MAP.md)
