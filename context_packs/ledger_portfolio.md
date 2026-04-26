# Ledger Portfolio Context Pack

## Purpose

Work on canonical ledger schema, bet identity, dedupe, appends, blocked candidates, and portfolio gates against open official ledger exposure.

## Include by Default

- `vcbet/domain/contracts.py`
- `vcbet/core/ledger_manager.py`
- `vcbet/ledger/schema.py`
- `vcbet/ledger/identity.py`
- `vcbet/ledger/repository.py`
- `vcbet/ledger/append_use_case.py`
- `vcbet/core/ledger_portfolio_gate.py`
- `vcbet/settlement/report_ledger.py`
- `scripts/dedupe_ledger.py`
- `tests/test_ledger_portfolio_gate.py`
- `tests/test_ledger_provenance.py`

## Include Only If Needed

- `vcbet/core/line_selector.py` when market family or correlation affects ledger exposure.
- `vcbet/core/pipeline/output_writer.py` when the daily pipeline appends to the ledger.
- `vcbet/core/pipeline/quality_report.py` when pipeline quality or provenance reports include ledger/portfolio outcomes.
- `vcbet/core/pipeline_ev.py` only as the compatibility entrypoint when orchestration behavior is part of the task.
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
- Read-modify-write ledger flows must use `update_ledger(path, mutator)` so the ledger lock covers read, decision, mutation, and atomic write.
- `LedgerRepository.read() -> list[BetRecord]` and `append() -> LedgerAppendResult` are the Phase 2 domain-facing ledger boundary.
- The old tuple-returning append API remains compatible for existing callers.
- Ledger schema normalization must preserve existing columns and fill missing expected columns safely.
- Open-ledger duplicate, correlated, and contradictory picks must be blocked or recorded for review, not appended silently.
- Dedupe must use stable bet identity, not incidental row order.
- pandas remains inside repository internals for CSV compatibility.

## Validation Commands

- `python3 -m pytest tests/test_ledger_portfolio_gate.py tests/test_ledger_provenance.py`
- Add `tests/test_temporal_contract.py` when provenance fields or source snapshot references change.

## Known Hotspots

- `vcbet/core/ledger_manager.py` is now a compatibility entrypoint after the Phase 1 ledger split.
- Ledger implementation is split across `vcbet/ledger/schema.py`, `identity.py`, `repository.py`, and `append_use_case.py`.
- CSV currently acts as database, DTO, log, API contract, and operational state for ledger flows.
- Phase 2 added typed ledger contracts, but not all application code is converted.

## Refactor Direction

Split ledger schema/identity rules from CSV repository writes. Keep an explicit append use case and domain-facing repository that return append, blocked, duplicate, and provenance outcomes without changing canonical CSV schema. Phase 3 service automation has not started.
