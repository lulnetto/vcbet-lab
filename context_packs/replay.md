# Replay Context Pack

## Purpose

Work on deterministic replay runs, source run resolution, config comparisons, replay scorecards, summary payloads, and replay settlement context.

## Include by Default

- `vcbet/replay/replay_pipeline.py`
- `scripts/build_replay_catalog.py`
- `tests/test_replay_comparison_scorecard.py`
- `tests/test_temporal_contract.py`

## Include Only If Needed

- `vcbet/core/pipeline_ev.py` when replay invokes or mirrors the daily pipeline.
- `vcbet/core/ledger_manager.py` when replay ledger summaries are involved.
- `vcbet/settlement/settlement_engine.py` when replay settlement changes.
- `vcbet/service/api.py` when replay routes or summary loading change.
- `vcbet/service/static/js/screens.js` when replay UI display changes.
- `configs/legacy_v2.json`, `configs/champion_strict.json`, or `configs/intermediate_balanced.json` for comparison presets.
- One replay/run manifest or summary sample only under the replay exception in `docs/LLM_CONTEXT_RULES.md`.

## Exclude

- `data/replays/**` by default
- `data/runs/**` by default
- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- full ledgers

## Key Invariants

- Replay must resolve source odds and xG snapshots from manifest/provenance without guessing when evidence is incomplete.
- Replay summaries must distinguish baseline, candidate config, recommendation context, and replay input contract.
- Comparisons must preserve pick identity, market family, scorecard metrics, and temporal contract status.
- Replay artifacts are generated output and should not become default LLM context.

## Validation Commands

- `python3 -m pytest tests/test_replay_comparison_scorecard.py tests/test_temporal_contract.py`
- Add `tests/test_ledger_provenance.py` when replay ledger summaries or provenance fields change.

## Known Hotspots

- `vcbet/replay/replay_pipeline.py` is roughly 782 LOC and mixes source resolution, subprocess orchestration, scoring, settlement, and summary shaping.
- Service and frontend replay screens depend on replay summary payload shape.

## Refactor Direction

Extract source-run resolution, comparison scoring, replay execution, and summary DTO creation into separate application services. Keep generated replay directories behind repository/read-model boundaries.
