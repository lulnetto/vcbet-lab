# Market Normalization Context Pack

## Purpose

Work on translating raw bookmaker market text and selections into normalized market type, scope, side, line, target role, target team, and status.

## Include by Default

- `vcbet/core/market_normalizer.py`
- `vcbet/core/market_thresholds.py`
- `tests/test_market_normalizer.py`

## Include Only If Needed

- `vcbet/collectors/odds_collector.py` when the task touches collected odds rows.
- `vcbet/collectors/closing_odds_collector.py` when closing odds matching depends on normalized markets.
- `vcbet/core/pipeline/input_loader.py` and `vcbet/core/pipeline/filtering_stage.py` when normalized odds flow into candidate generation.
- `vcbet/core/pipeline_ev.py` only as the compatibility entrypoint when daily-run orchestration is involved.
- `vcbet/core/team_matcher.py` when team-total target matching is involved.
- `configs/legacy_v2.json`, `configs/champion_strict.json`, or `configs/intermediate_balanced.json` when allowed markets or thresholds are relevant.

## Exclude

- `data/**`
- `dev_asset/**`
- `legacy/history_snapshots/**`
- caches and `__pycache__`
- logs
- generated runs, replays, and results
- full ledgers

## Key Invariants

- First-half, alternative, and unsupported markets must not be silently normalized as full-time primary markets.
- Normalized rows must preserve enough source text to debug bookmaker parsing.
- Market scope, side, line, and target team fields must remain stable for downstream pricing, selection, ledger, replay, and closing odds matching.
- Normalization may use pandas at adapter boundaries, but domain rules should be extractable away from dataframe mutation.

## Validation Commands

- `python3 -m pytest tests/test_market_normalizer.py`
- Add `tests/test_decision_architecture.py` if normalized market fields change selection behavior.

## Known Hotspots

- `vcbet/core/market_normalizer.py` is just over the 300 LOC target.
- `vcbet/collectors/odds_collector.py`, `vcbet/core/pipeline/input_loader.py`, and `vcbet/core/pipeline/filtering_stage.py` are risky call sites because collection, normalization, and orchestration remain tightly coupled.

## Refactor Direction

Extract pure market parsing rules from dataframe adapters. Keep collectors responsible for raw capture and application code responsible for applying normalization to batches.
