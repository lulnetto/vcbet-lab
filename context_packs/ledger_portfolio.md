# Ledger Portfolio Context Pack

## Purpose

Work on canonical ledger schema, bet identity, dedupe, appends, blocked candidates, and portfolio gates against open official ledger exposure.

## Include by Default

- `vcbet/core/ledger_manager.py`
- `vcbet/core/ledger_portfolio_gate.py`
- `vcbet/settlement/report_ledger.py`
- `scripts/dedupe_ledger.py`
- `tests/test_ledger_portfolio_gate.py`
- `tests/test_ledger_provenance.py`

## Include Only If Needed

- `vcbet/core/line_selector.py` when market family or correlation affects ledger exposure.
- `vcbet/core/pipeline_ev.py` when pipeline appends to the ledger.
- `vcbet/settlement/settlement_engine.py` when final status or result units affect ledger rows.
- `vcbet/service/dashboard.py` when ledger data is surfaced in summaries.
- `tests/test_temporal_contract.py` when provenance or snapshot fields are involved.
- Tiny ledger excerpts only under the ledger exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/**` by default, including the full canonical ledger
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results

## Key Invariants

- The canonical official ledger is `data/history/bets_ledger.csv`.
- Official appends must pass through `append_new_picks_to_ledger`.
- Ledger schema normalization must preserve existing columns and fill missing expected columns safely.
- Open-ledger duplicate, correlated, and contradictory picks must be blocked or recorded for review, not appended silently.
- Dedupe must use stable bet identity, not incidental row order.

## Validation Commands

- `python3 -m pytest tests/test_ledger_portfolio_gate.py tests/test_ledger_provenance.py`
- Add `tests/test_temporal_contract.py` when provenance fields or source snapshot references change.

## Known Hotspots

- `vcbet/core/ledger_manager.py` is over 300 LOC and mixes schema, identity, IO, blocked artifacts, and append behavior.
- CSV currently acts as database, DTO, log, API contract, and operational state for ledger flows.

## Refactor Direction

Split ledger schema/identity rules from CSV repository writes. Keep an explicit append use case that receives selected picks and returns append, blocked, and provenance outcomes.
