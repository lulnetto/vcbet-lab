# Selection Policy Context Pack

## Purpose

Work on candidate eligibility, safety gates, confidence, risk flags, portfolio exposure before ledger append, correlation, and top-pick selection.

## Include by Default

- `vcbet/core/line_selector.py`
- `vcbet/core/decision_policy.py`
- `vcbet/core/risk_policy.py`
- `vcbet/core/pick_filter.py`
- `vcbet/core/correlation_rules.py`
- `vcbet/core/market_thresholds.py`
- `vcbet/core/strategy_config.py`
- `tests/test_decision_architecture.py`
- `tests/test_pick_safety_gates.py`
- `tests/test_portfolio_risk.py`

## Include Only If Needed

- `vcbet/core/pricing_engine.py` when EV/probability drives eligibility.
- `vcbet/core/pick_features.py` when candidate row fields are changing.
- `vcbet/core/ledger_portfolio_gate.py` when official ledger exposure differs from in-run exposure.
- `vcbet/core/pipeline_ev.py` for orchestration call sites.
- `vcbet/service/dashboard.py` when rejection or flag summaries are displayed.
- `configs/legacy_v2.json`, `configs/champion_strict.json`, or `configs/intermediate_balanced.json` for config-specific behavior.

## Exclude

- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results
- full ledgers

## Key Invariants

- Rejected candidates must carry clear status and reason fields.
- Accepted picks must have stable bet identity, selection status, confidence, stake, and risk flag semantics.
- Duplicate, near-duplicate, contradictory, and correlated picks must be handled deterministically.
- Config presets must continue to control thresholds without hard-coding policy into orchestration.

## Validation Commands

- `python3 -m pytest tests/test_decision_architecture.py tests/test_pick_safety_gates.py tests/test_portfolio_risk.py`
- Add `tests/test_ledger_portfolio_gate.py` when open-ledger exposure is involved.

## Known Hotspots

- `vcbet/core/line_selector.py` is over 500 LOC and mixes selection, exposure tracking, correlation, and rejection shaping.
- `vcbet/core/decision_policy.py` is near the 300 LOC target and concentrates identity, confidence, and acceptance policy.
- `vcbet/core/pipeline_ev.py` is a large call-site hotspot for this domain.

## Refactor Direction

Separate pure policy decisions from dataframe grouping and output shaping. Target small strategy/policy functions with explicit candidate and rejection contracts.
