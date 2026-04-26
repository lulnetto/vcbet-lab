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
- `vcbet/core/pipeline/filtering_stage.py` for daily pipeline filtering and final-pick selection call sites.
- `vcbet/core/pipeline/output_writer.py` when selected picks are written or ledger appends are involved.
- `vcbet/core/pipeline_ev.py` only as the compatibility entrypoint when orchestration behavior is part of the task.
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
- `vcbet/core/pipeline/filtering_stage.py` and `vcbet/core/pipeline/output_writer.py` are the daily pipeline call sites for this domain; `vcbet/core/pipeline_ev.py` should stay a thin compatibility orchestrator.

## Fase 1.5 Correlation Audit Notes

- Over goals + BTTS: run-level selection treats most `total_goals`/`btts` pairs as medium correlation, with `Under` + `BTTS No` classified high. The official open-ledger gate blocks any open cross-market exposure among goals total, team goals, and BTTS. Bettor decision needed before making run-level selection as strict as the ledger gate or before allowing ledger coexistence.
- Team total + match total: current logic is mostly medium, with one broad low-correlation carveout for team `Over` low line plus match `Under` high line. It does not encode full deterministic incompatibility intervals such as a team-total over line that makes a lower match-total under line impossible. Bettor decision needed on exact interval rules and whether they should reject or downgrade.
- Handicap + moneyline equivalents: no `moneyline`/1X2 market family is currently normalized in the active selection path. If that market is introduced, define equivalence with handicap lines such as 0, -0.25, -0.5, and +0.5 before enabling coexistence.
- Over/under contradictory lines: same-family opposite sides are rejected only when lines are equal or near within `contradictory_line_tolerance`. Wider impossible pairs, for example `Over 3.5` with `Under 2.5`, are currently handled as medium correlation rather than contradiction. Bettor decision needed before changing this from tolerance-based matching to interval-based contradiction detection.

## Refactor Direction

Separate pure policy decisions from dataframe grouping and output shaping. Target small strategy/policy functions with explicit candidate and rejection contracts.
