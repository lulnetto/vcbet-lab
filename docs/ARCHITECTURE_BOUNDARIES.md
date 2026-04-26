# Architecture Boundaries

This document turns the audit diagnosis into development contracts for future VCBet work.

## Current Diagnosis

- Phase 0 stabilization is complete after hardening ledger writes, snapshot freshness, settlement statuses, job-store durability, and replay status/freshness regressions.
- Phase 1 mechanical splits are complete for ledger, replay, and team identity while preserving public compatibility entrypoints.
- `vcbet/core/ledger_manager.py`, `vcbet/replay/replay_pipeline.py`, and `vcbet/core/team_registry.py` are compatibility entrypoints. Implementation now lives under `vcbet/ledger/`, `vcbet/replay/`, and `vcbet/team_identity/`.
- `vcbet/core/pipeline_ev.py` remains the daily pipeline compatibility entrypoint, while stage implementation details live under `vcbet/core/pipeline/`.
- CSV currently remains the operational storage backend for ledger, results, runtime artifacts, and read models.
- `vcbet/ledger/repository.py` owns atomic CSV replacement and transactional ledger read-modify-write updates through `update_ledger(path, mutator)`.
- Typed domain contracts have not been introduced yet. Phase 2 has not started.
- pandas still leaks across domain-adjacent areas and should be reduced one boundary at a time in Phase 2.

## Target Dependency Direction

```text
collectors/adapters
    -> normalized inputs
    -> domain core
    -> application use cases
    -> repositories/output writers
    -> service/CLI/frontend
```

Lower layers must not import upper layers. Runtime adapters may translate external data into domain contracts, but domain logic should not know how data was fetched, stored, served, or displayed.

## Allowed Dependencies

- `service -> application -> domain`
- `cli -> application -> domain`
- `scripts -> application/adapters`
- `adapters -> domain contracts`

## Forbidden Dependencies

- `core -> service`
- `core -> scripts`
- `service -> scripts`
- `domain -> pandas`
- `domain -> filesystem`
- `domain -> subprocess`
- `domain -> FastAPI`

Current code may still violate some of these boundaries. New work should not deepen those violations; refactors should reduce them one domain at a time.

## Domain Boundaries

- `team_identity`: team names, registry aliases, review queues, confidence, and matching contracts.
- `market_normalization`: raw bookmaker market text to normalized market type, scope, side, line, and target.
- `pricing`: probability, fair odds, EV, lambda, and market pricing formulas.
- `decision_selection`: candidate eligibility, risk flags, confidence, line selection, correlation, and exposure policy before ledger append.
- `ledger`: canonical bet identity, ledger schema normalization, append safety, dedupe, and portfolio gate.
- `settlement`: result ingestion, score matching, bet settlement, final status, and result units.
- `replay`: deterministic reruns, source run resolution, comparison summaries, replay scorecards, and replay settlement context.
- `service`: FastAPI routes, request/response schemas, job orchestration, catalog loading, and dashboard payloads.
- `frontend`: static HTML/CSS/JS state, API calls, screens, tables, and operator workflows.

## File-Size Rule

- Product Python files should trend below 300 LOC.
- JS screen files should trend below 300 LOC.
- Orchestration files should be thin.

Large files are not automatically wrong, but they are refactor candidates when a task is already working inside that domain. Prefer extracting named use cases, repositories, adapters, and UI screen modules over adding more branches to a hotspot.

## Phase Summary

### Phase 0: Critical Stabilization

Complete. Canonical ledger writes use locking and atomic replacement; read-modify-write flows use transactional ledger updates; snapshot freshness is mandatory through `max_snapshot_age_hours`; stale snapshots are rejected before EV calculation; settlement distinguishes `OPEN`, `UNMATCHED`, postponed, voided, and settled states; `sofascore_event_id` survives pipeline export and ledger compatibility; job store JSON writes are atomic.

### Phase 1: Mechanical Boundaries

Complete. Remaining hotspots were split mechanically where planned, keeping compatibility imports stable:

- ledger implementation under `vcbet/ledger/`
- replay implementation under `vcbet/replay/`
- team identity implementation under `vcbet/team_identity/`

### Phase 2: Contracts and Domain Cleanup

Next. Introduce typed contracts gradually at critical boundaries and move pandas toward adapters/borders. Do not redesign ledger storage as part of Phase 2 unless explicitly scoped.

### Later Phases

Phase 3 service robustness and automation, and Phase 4 UI improvements, remain future work. Scheduler implementations must not bypass ledger transactional update helpers.
