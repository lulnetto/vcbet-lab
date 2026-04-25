# Data Model

VCBet keeps runtime data as files under `data/`. The product source of truth remains simple and explicit: the canonical official betting ledger is `data/history/bets_ledger.csv`.

## Ledgers

- `data/history/bets_ledger.csv` is the only canonical official ledger.
- Other ledger-like files may exist for sandbox, replay, debug, rerun, or legacy development work.
- Ledger-like files outside the canonical path should be treated as non-official unless a human explicitly promotes them.
- The official ledger schema is not changed by catalog generation or cleanup tooling.
- `event_url` is optional for backward compatibility, but recommended because it enables closing odds collection.
- Official appends pass through a ledger-level portfolio gate that checks open/unsettled exposure already present in the canonical ledger. Blocked cross-run/cross-config duplicates, correlations, and contradictions are written to a review artifact instead of being appended silently.

Closing odds are stored in closing-specific fields (`closing_odd`, `closing_bookmaker`, `closing_snapshot_time`, `closing_source`, `closing_update_status`, `closing_update_error`). They must not overwrite `odd_entrada`, model odds, or other original decision fields.

## Runs

Runs live under `data/runs/<target-date>/<run-id>/`. One folder per run is intentional because each run carries a coherent set of snapshots, picks, quality reports, config snapshots, and `run_manifest.json`.

Run folders are not collapsed into daily append files. Keeping the folder boundary preserves provenance, makes replay/debug comparison easier, and avoids mixing artifacts from different configurations or collection times.

`data/runs/catalog.jsonl` is the navigable index for run folders. It is generated from existing folders and manifests, tolerates old partial manifests, and stores project-relative paths when possible.

The service exposes this catalog as read-only UI entity data. The catalog is a local runtime artifact and is not required to be versioned.

## Replays

Replays live under `data/replays/<target-date>/<replay-id>/`. Replay folders may contain replay ledgers, replay results, comparison summaries, picks, quality reports, config snapshots, and `run_manifest.json`.

`data/replays/catalog.jsonl` is the navigable index for replay and comparison folders. It prepares the UI and operators to select known artifacts without manually typing paths.

The service exposes this catalog as read-only UI entity data. If it is missing, the UI should fall back to a clear empty state and manual `Avançado` paths.

## Results

`data/results/` contains result collection outputs and overrides that may be needed by settlement flows. Result files are classified conservatively because an output can affect settlement even when it looks small.

Debug result captures under paths such as `data/results/_debug/` are runtime/debug artifacts, not product sources of truth.

## Team Registry

Approved Betano ↔ FootyStats team aliases live in `configs/team_registry/betano_footystats_aliases.csv` so they can be reviewed and versioned with code/config changes.

Runtime registry maintenance artifacts live under `data/team_registry/`, including `alias_review_pending.csv` for ambiguous candidates and `betano_teams_snapshot.json` for the latest sync snapshot. These are generated artifacts and should not be promoted to source of truth without review.

The official matching order is registry-approved alias, legacy `alias_times.json`, exact match, then fuzzy fallback. Fuzzy matches remain safety-gated for official picks; recurring fuzzy or unresolved cases are registry maintenance signals.

## Service Jobs And Logs

`data/service/jobs/` and `data/service/logs/` contain runtime service metadata. They are useful for debugging recent operations, but stale job/log files are not official betting history.

## Runtime Artifacts

Runtime artifacts include debug captures, stale service jobs/logs, old reruns, sandbox ledgers, and replay outputs. Cycle 7 tooling inventories them and can archive clearly obsolete items under `data/_archive/pre_cycle7_cleanup/` while preserving relative paths.

Cleanup is dry-run by default. No cleanup tool should touch `data/history/bets_ledger.csv`, generated catalogs, configs, source code, or files outside `data/`.

## Source Of Truth Rules

- Official betting history: `data/history/bets_ledger.csv`.
- Run provenance: the run folder plus its `run_manifest.json`.
- Replay provenance: the replay folder plus its `run_manifest.json` or summary file.
- Catalogs are indexes, not primary data. They can be regenerated from existing artifacts.
- Partial historical manifests remain valid historical records.
- Approved team aliases: `configs/team_registry/betano_footystats_aliases.csv`.
