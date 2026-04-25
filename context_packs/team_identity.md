# Team Identity Context Pack

## Purpose

Work on team normalization, Betano-to-FootyStats alias matching, registry parsing, approved/quarantine CSVs, review queues, and service endpoints for team registry operations.

## Include by Default

- `vcbet/core/team_matcher.py`
- `vcbet/core/team_registry.py`
- `vcbet/service/team_registry_api.py`
- `scripts/sync_team_aliases.py`
- `configs/team_registry/betano_footystats_aliases.csv`
- `configs/team_registry/betano_footystats_aliases_quarantine.csv`
- `tests/test_team_registry.py`
- `tests/test_team_registry_api.py`

## Include Only If Needed

- `scripts/approve_alias_review.py` when legacy alias approval flow is involved.
- `vcbet/core/risk_policy.py` when alias confidence affects safety gates.
- `vcbet/core/pipeline_ev.py` when team matching affects daily candidate generation.
- `vcbet/collectors/odds_collector.py` or `vcbet/collectors/footystats_xg_collector.py` when raw team sources change.
- `vcbet/service/static/js/screens.js` when team registry UI behavior changes.
- Tiny runtime review queue excerpts only under the aliases/team registry exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/team_registry/**` by default
- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results
- full ledgers

## Key Invariants

- Approved registry aliases must represent valid team identities, not league pages or standings labels.
- Quarantined aliases must not be silently promoted into approved mappings.
- Matching confidence, ambiguity reason, review status, and source metadata must remain explainable.
- Alias review should preserve pending rows unless an approve, reject, or update action explicitly changes them.

## Validation Commands

- `python3 -m pytest tests/test_team_registry.py tests/test_team_registry_api.py`
- Add `tests/test_decision_architecture.py` when identity confidence changes candidate safety behavior.

## Known Hotspots

- `vcbet/core/team_registry.py` is roughly 653 LOC and combines parsing, scoring, matching, registry IO, and review writing.
- `vcbet/service/team_registry_api.py` is over 300 LOC and currently connects service operations to script-level sync.
- `scripts/sync_team_aliases.py` handles network/browser-style sync behavior and should be isolated from pure identity logic.

## Refactor Direction

Separate identity scoring/parsing from CSV registry repositories and sync adapters. Route service operations through an application use case instead of importing scripts directly.
