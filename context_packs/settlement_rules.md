# Settlement Rules Context Pack

## Purpose

Work on result collection, result matching, automatic settlement, manual overrides, status transitions, void/postponed/unmatched handling, and final ledger settlement fields.

## Include by Default

- `vcbet/settlement/settlement_engine.py`
- `vcbet/settlement/report_ledger.py`
- `vcbet/collectors/results_collector.py`
- `vcbet/ledger/schema.py`
- `vcbet/core/ledger_manager.py`
- `tests/test_ledger_provenance.py`
- `tests/test_service_composed_workflows.py`

## Include Only If Needed

- `vcbet/collectors/closing_odds_collector.py` when closing odds fields interact with settled rows.
- `vcbet/service/closing_watcher.py` when watcher behavior depends on open/settled status.
- `vcbet/service/dashboard.py` when operator summaries or status counts change.
- `vcbet/service/routes/*.py` when service settlement endpoints change.
- `vcbet/replay/*.py` when replay settlement summaries or comparison artifacts change.
- Result CSV headers or tiny row samples only under the result exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/results/**` by default.
- `data/history/**` by default.
- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs and replays
- full ledgers

## Result Collection Concerns

- Collectors ingest external match results and should preserve source provenance, confidence, and notes.
- Transient fetch failures should not be confused with a confirmed missing result.
- Collected results must be explicit enough for the settlement engine to distinguish settled, postponed, void, open, and unmatched situations.

## Matching Concerns

- Structured identifiers, especially `sofascore_event_id`, should be used before fuzzy or name/date matching when present.
- Missing identifiers must not destroy compatibility with older ledger rows.
- Matching confidence and notes should remain visible to operators and downstream reports.
- If matching behavior changes, add a narrow regression test before expanding the change.

## Status Transitions

- `OPEN` means the match is not ready to settle yet or remains legitimately pending.
- `UNMATCHED` means expected result lookup failed and the bet needs manual review or later reprocessing.
- Settled states must preserve existing win/loss/push/half-result semantics.
- `VOIDED` and postponed behavior must remain distinct where already supported.
- Future bets must not be marked `UNMATCHED` prematurely; kickoff time and expected result availability matter.

## Override Concerns

- Manual overrides take precedence where the current settlement engine already allows them.
- Override fields must preserve auditability: operator-provided status/result fields should not erase automatic provenance silently.
- UI or API changes should show the automatic result before accepting a manual override.

## Void, Postponed, and Unmatched Concerns

- Voided/postponed rows should not accrue result units as settled wins or losses.
- Unmatched rows should be excluded from open exposure calculations unless a specific policy says otherwise.
- Closing odds and watcher flows should not keep retrying rows that are no longer genuinely open.
- Reprocessing should be able to revisit unmatched rows when new results become available.

## Validation Commands

- `python3 -m pytest tests/test_ledger_provenance.py tests/test_service_composed_workflows.py`
- `bash scripts/validate_release.sh`
- `git diff --check`

## Refactor Direction

Separate result collection adapters, result matching, settlement status transitions, override resolution, and ledger persistence. Settlement rules should be testable from normalized ledger rows and normalized result rows without mutating runtime data.
