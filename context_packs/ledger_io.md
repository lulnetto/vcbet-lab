# Ledger IO Context Pack

## Purpose

Work on canonical ledger schema, bet identity, CSV repository IO, append use cases, file locking, dedupe, and compatibility reads for old ledger files.

## Include by Default

- `vcbet/domain/contracts.py`
- `vcbet/core/ledger_manager.py`
- `vcbet/ledger/schema.py`
- `vcbet/ledger/identity.py`
- `vcbet/ledger/repository.py`
- `vcbet/ledger/append_use_case.py`
- `vcbet/core/ledger_portfolio_gate.py`
- `tests/test_ledger_portfolio_gate.py`
- `tests/test_ledger_provenance.py`

## Include Only If Needed

- `vcbet/core/pipeline/output_writer.py` when run artifacts or official append orchestration change.
- `vcbet/core/pipeline_ev.py` when the public `processar_pipeline` append path changes.
- `vcbet/settlement/settlement_engine.py` when final ledger status or settlement fields change.
- `vcbet/settlement/report_ledger.py` when operator-facing ledger reports change.
- `vcbet/service/dashboard.py` when ledger summaries are surfaced through the service.
- `scripts/dedupe_ledger.py` when offline ledger maintenance behavior changes.
- Tiny ledger excerpts only under the ledger exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/**` by default, including the full canonical ledger.
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results

## Schema Concerns

- The canonical ledger is `data/history/bets_ledger.csv`.
- CSV remains the canonical operational storage backend for now; SQLite/Postgres is future work and has not been implemented.
- `vcbet/ledger/schema.py` owns expected columns, schema metadata, compatibility normalization, and structured field derivation such as `sofascore_event_id`.
- Reads must tolerate old CSVs that are missing newer columns.
- Writes must preserve schema order for known columns and retain unknown historical columns after the known schema.
- Adding a column is a compatibility event and needs idempotent derivation or safe blank defaults.
- Public compatibility imports remain available through `vcbet/core/ledger_manager.py`; new work should prefer the split `vcbet/ledger/*` modules only when changing ledger internals.
- Phase 2 added `BetRecord` and `LedgerAppendResult` in `vcbet/domain/contracts.py`.

## Repository Concerns

- `vcbet/ledger/repository.py` owns CSV load/save, canonical file creation, file locking, and atomic replace behavior.
- `LedgerRepository.read() -> list[BetRecord]` and `append() -> LedgerAppendResult` are now the domain-facing ledger boundary.
- The repository still uses pandas internally for CSV compatibility; that is intentional adapter/repository behavior, not domain leakage.
- All canonical ledger writes must use the repository lock path.
- `update_ledger(path, mutator)` is the required API for read-modify-write flows. It holds the ledger lock through the full `ensure -> read -> mutate -> atomic write` cycle.
- File locks should cover the full read-gate-append-write sequence when the caller is deciding whether to append.
- Atomic writes should avoid partial CSVs after crashes or interrupted service jobs.
- `save_ledger()` or final-write-only locking is not enough when the caller has loaded a DataFrame, made decisions, and then writes it back.

## Append Concerns

- `vcbet/ledger/append_use_case.py` owns conversion from selected picks to ledger rows, blocked candidate artifact writing, dedupe, and append result reporting.
- Official appends must pass through `append_new_picks_to_ledger`.
- The old tuple-returning append API remains compatible; detailed append reporting is available through `LedgerAppendResult`.
- Scheduler, service, CLI, and replay-triggered writes must not bypass the append use case.
- Append behavior must not change stake, EV, market, or selection thresholds.
- Pipeline exports must preserve structured event identifiers, including `sofascore_event_id` and `source_event_id`, so the canonical ledger can use them directly during settlement.

## Locking Concerns

- The lock must protect every canonical ledger write path.
- Settlement, closing odds collection, closing watcher jobs, service-triggered jobs, and scheduler-triggered jobs must use transactional ledger helpers for any read-modify-write update.
- Do not load the ledger, mutate a stale DataFrame, and then call `save_ledger()` outside the same lock; a concurrent append between load and save can be lost.
- File locking alone does not replace portfolio gate serialization when two runs can read the same open exposure before appending.
- Lock files are coordination artifacts and should not be treated as ledger data.

## Dedupe Concerns

- Dedupe uses stable bet identity from `vcbet/ledger/identity.py`.
- Dedupe semantics must remain stable across mechanical splits.
- Existing historical row order should not become a hidden identity component.
- Duplicate or correlated candidates should be blocked or reported, not silently appended.

## Validation Commands

- `python3 -m pytest tests/test_ledger_portfolio_gate.py tests/test_ledger_provenance.py`
- `bash scripts/validate_release.sh`
- `git diff --check`

## Refactor Direction

Keep ledger schema, identity, repository IO, and append orchestration separate. Domain/application logic should consume `BetRecord` and `LedgerAppendResult` through `LedgerRepository`, not write CSV directly. Phase 3 has not started; automation must continue to use transactional ledger helpers.
