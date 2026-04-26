# Replay Context Pack

## Purpose

Work on deterministic replay runs, source run resolution, config comparisons, replay scorecards, summary payloads, and replay settlement context.

## Include by Default

- `vcbet/replay/replay_pipeline.py`
- `vcbet/replay/source_resolver.py`
- `vcbet/replay/execution.py`
- `vcbet/replay/scoring.py`
- `vcbet/replay/summary_builder.py`
- `scripts/build_replay_catalog.py`
- `tests/test_replay_comparison_scorecard.py`
- `tests/test_temporal_contract.py`

## Include Only If Needed

- `vcbet/core/pipeline_ev.py` when replay invokes the daily pipeline compatibility entrypoint.
- `vcbet/core/pipeline/input_loader.py`, `vcbet/core/pipeline/output_writer.py`, and `vcbet/core/pipeline/quality_report.py` when replay mirrors daily pipeline implementation details.
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
- Replay freshness is historical freshness, not wall-clock freshness. Validate snapshots against the source run's decision/generated timestamp.
- Missing freshness provenance must fail explicitly with `replay_freshness_reference_missing`; do not bypass snapshot validation for replay.
- Replay summaries must distinguish baseline, candidate config, recommendation context, and replay input contract.
- Replay summaries must report `open`, `unmatched`, `postponed`, and `voided` separately. Postponed or voided rows must not inflate open counts.
- Comparisons must preserve pick identity, market family, scorecard metrics, and temporal contract status.
- Replay artifacts are generated output and should not become default LLM context.

## Validation Commands

- `python3 -m pytest tests/test_replay_comparison_scorecard.py tests/test_temporal_contract.py`
- Add `tests/test_ledger_provenance.py` when replay ledger summaries or provenance fields change.

## Known Hotspots

- `vcbet/replay/replay_pipeline.py` is now a compatibility entrypoint after the Phase 1 split.
- `vcbet/replay/source_resolver.py`, `execution.py`, `scoring.py`, and `summary_builder.py` hold the implementation slices.
- Replay execution currently invokes `vcbet.core.pipeline_ev` through the configured Python subprocess. A direct call can be considered later only if it preserves CLI compatibility and artifact outputs.
- Service and frontend replay screens depend on replay summary payload shape.

## Refactor Direction

Extract source-run resolution, comparison scoring, replay execution, and summary DTO creation into separate application services. Keep generated replay directories behind repository/read-model boundaries.
