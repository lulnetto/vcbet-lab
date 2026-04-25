# Architecture Boundaries

This document turns the audit diagnosis into development contracts for future VCBet work.

## Current Diagnosis

- VCBet is still closer to organized scripts than modular architecture.
- CSV currently acts as DB, DTO, log, API contract, and operational state.
- pandas leaks across boundaries.
- `vcbet/service/api.py`, `vcbet/core/pipeline_ev.py`, `vcbet/replay/replay_pipeline.py`, and `vcbet/service/static/js/screens.js` were identified as cognitive hotspots.
- `vcbet/core/pipeline_ev.py` now remains the daily pipeline compatibility entrypoint, while stage implementation details live under `vcbet/core/pipeline/`; that split was intended to preserve behavior.

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

### Phase 1: Context and Contracts

Establish LLM context rules, domain context packs, dependency direction, and file-size expectations. Keep production behavior unchanged. Use narrow tests and briefing docs to target one domain at a time.

### Phase 2: Application Boundaries

Continue extracting use cases out of hotspots such as `replay_pipeline.py`, `service/api.py`, `screens.js`, and the implementation stages under `vcbet/core/pipeline/`. Keep `pipeline_ev.py` as compatibility orchestration, and introduce repository/output-writer boundaries around CSV reads and writes while preserving current file formats and operator workflows.

### Phase 3: Domain Purity and Storage Evolution

Move pandas, filesystem, subprocess, FastAPI, and browser concerns out of domain logic. Replace CSV-as-everything with explicit contracts for persistence, DTOs, logs, API payloads, and operational state, after tests cover the current behavior.
