# Settlement Context Pack

## Purpose

Work on result ingestion, score matching, manual overrides, bet settlement, final status fields, closing odds interactions, and result-unit calculations.

## Include by Default

- `vcbet/settlement/settlement_engine.py`
- `vcbet/settlement/report_ledger.py`
- `vcbet/collectors/results_collector.py`
- `tests/test_ledger_provenance.py`
- `tests/test_service_composed_workflows.py`

## Include Only If Needed

- `vcbet/core/ledger_manager.py` when reading or writing ledger rows.
- `vcbet/collectors/closing_odds_collector.py` when closing odds fields affect final records.
- `scripts/update_closing_odds.py` when the closing odds command path is involved.
- `vcbet/service/commands.py` when service-triggered results or settlement jobs change.
- `vcbet/service/api.py` when settlement routes or job endpoints change.
- `tests/test_closing_watcher.py` for closing odds watcher behavior.
- Result CSV headers or tiny row samples only under the settlement/result exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/results/**` by default
- `data/history/**` by default
- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs and replays
- full ledgers

## Key Invariants

- Manual overrides must take precedence over automatic result fields where designed.
- Settlement must handle total-like markets, asian handicap, voided, postponed, open, and pending states consistently.
- Result-unit calculations must use executed odds and executed stake when present.
- Settlement must preserve provenance, confidence, source, and note fields.

## Validation Commands

- No narrow settlement-only test currently exists.
- Closest available: `python3 -m pytest tests/test_ledger_provenance.py tests/test_service_composed_workflows.py`
- Add `tests/test_closing_watcher.py` when closing odds watcher behavior changes.

## Known Hotspots

- `vcbet/settlement/settlement_engine.py` is over 300 LOC and mixes parsing, matching, settlement rules, overrides, and IO.
- `vcbet/collectors/results_collector.py` is large and combines external result collection with matching logic.

## Refactor Direction

Separate result collection adapters, result matching, settlement rules, and ledger repository writes. Introduce a settlement use case that accepts ledger entries plus normalized results and returns final field updates.
