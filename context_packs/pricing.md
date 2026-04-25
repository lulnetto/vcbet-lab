# Pricing Context Pack

## Purpose

Work on probability, fair odds, EV, lambda calculation, and the pricing fields emitted into candidates and dashboards.

## Include by Default

- `vcbet/core/pricing_engine.py`
- `vcbet/core/pick_features.py`
- `tests/test_pricing_engine.py`
- `tests/test_pricing_outputs.py`

## Include Only If Needed

- `vcbet/core/pipeline_ev.py` for pricing call sites in the daily pipeline.
- `vcbet/core/decision_policy.py` when EV or confidence thresholds affect eligibility.
- `vcbet/service/dashboard.py` when dashboard pricing payload fields are involved.
- `configs/legacy_v2.json`, `configs/champion_strict.json`, or `configs/intermediate_balanced.json` when config thresholds affect pricing interpretation.
- `tests/test_decision_architecture.py` when pricing changes affect candidate acceptance.

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
- Asian handicap and asian total quarter-line behavior must remain explicit and tested.
- `odd_justa`, `prob_model`, `ev_percent`, and pricing signal fields must remain consistent wherever candidates, ledgers, and dashboard payloads consume them.
- Pricing code should not read files, call services, or depend on FastAPI.

## Validation Commands

- `python3 -m pytest tests/test_pricing_engine.py tests/test_pricing_outputs.py`
- Add `tests/test_decision_architecture.py` when acceptance or confidence behavior changes.

## Known Hotspots

- `vcbet/core/pricing_engine.py` is currently below the 300 LOC target but contains dense probability logic.
- `vcbet/core/pipeline_ev.py` is a large orchestrator and should be treated as a call-site hotspot, not the pricing home.

## Refactor Direction

Keep formulas in a small domain module with typed pricing results. Move pandas row shaping and dashboard formatting to application or presentation code.
