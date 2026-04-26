# Pricing Context Pack

## Purpose

Work on probability, fair odds, EV, lambda calculation, and the pricing fields emitted into candidates and dashboards.

## Include by Default

- `vcbet/domain/contracts.py`
- `vcbet/core/pricing_engine.py`
- `vcbet/core/pick_features.py`
- `tests/test_pricing_engine.py`
- `tests/test_pricing_outputs.py`

## Include Only If Needed

- `vcbet/core/pipeline/pricing_stage.py` for pricing call sites in the daily pipeline.
- `vcbet/core/pipeline_ev.py` only as the compatibility entrypoint when orchestration behavior is part of the task.
- `vcbet/core/decision_policy.py` when EV or confidence thresholds affect eligibility.
- `vcbet/service/dashboard.py` when dashboard pricing payload fields are involved.
- `vcbet/reports/model_calibration.py` and `scripts/report_model_calibration.py` when model calibration, realized-frequency buckets, or report output are involved.
- `configs/legacy_v2.json`, `configs/champion_strict.json`, or `configs/intermediate_balanced.json` when config thresholds affect pricing interpretation.
- `tests/test_decision_architecture.py` when pricing changes affect candidate acceptance.
- `tests/test_model_calibration.py` when calibration bucket/report behavior changes.

## Exclude

- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results
- full ledgers

## Key Invariants

- Fair odds and EV must stay mathematically coherent for win, half-win, push, half-loss, and loss probabilities.
- Asian handicap and asian total quarter-line behavior must remain explicit and tested, including 0.75 and 1.25 lines.
- `odd_justa`, `prob_model`, `ev_percent`, and pricing signal fields must remain consistent wherever candidates, ledgers, and dashboard payloads consume them.
- Pricing code should not read files, call services, or depend on FastAPI.
- `vcbet/core/pricing_engine.py` is scalar and pandas-free after Phase 2. pandas shaping belongs in adapters such as `pick_features.py` and pipeline stages.
- `PricingResult` exists in `vcbet/domain/contracts.py`, but not all application code is converted to it yet.
- Model calibration compares `prob_model` against realized frequencies. It is read-only and separate from ROI/profitability reporting.

## Validation Commands

- `python3 -m pytest tests/test_pricing_engine.py tests/test_pricing_outputs.py`
- Add `tests/test_decision_architecture.py` when acceptance or confidence behavior changes.

## Known Hotspots

- `vcbet/core/pricing_engine.py` remains dense probability logic, but Phase 2 made it pandas-free internally.
- `vcbet/core/pipeline/pricing_stage.py` contains the daily pipeline pricing stage; `vcbet/core/pipeline_ev.py` should stay a thin compatibility orchestrator, not the pricing home.
- `vcbet/reports/model_calibration.py` is the first calibration report and should not be expanded into profitability claims without explicit scope.

## Refactor Direction

Keep formulas in a small scalar domain module with typed pricing results available at the boundary. Keep pandas row shaping and dashboard formatting in application or presentation code. Phase 3 has not started; service automation work should not change pricing formulas or calibration semantics.
