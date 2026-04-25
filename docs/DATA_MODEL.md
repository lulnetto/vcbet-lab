# Data Model

VCBet keeps runtime data as files under `data/`. The product source of truth remains simple and explicit: the canonical official betting ledger is `data/history/bets_ledger.csv`.

## Ledgers

- `data/history/bets_ledger.csv` is the only canonical official ledger.
- Other ledger-like files may exist for sandbox, replay, debug, rerun, or legacy development work.
- Ledger-like files outside the canonical path should be treated as non-official unless a human explicitly promotes them.
- The official ledger schema is not changed by catalog generation or cleanup tooling.

## Runs

Runs live under `data/runs/<target-date>/<run-id>/`. One folder per run is intentional because each run carries a coherent set of snapshots, picks, quality reports, config snapshots, and `run_manifest.json`.

Run folders are not collapsed into daily append files. Keeping the folder boundary preserves provenance, makes replay/debug comparison easier, and avoids mixing artifacts from different configurations or collection times.

`data/runs/catalog.jsonl` is the navigable index for run folders. It is generated from existing folders and manifests, tolerates old partial manifests, and stores project-relative paths when possible.

## Replays

Replays live under `data/replays/<target-date>/<replay-id>/`. Replay folders may contain replay ledgers, replay results, comparison summaries, picks, quality reports, config snapshots, and `run_manifest.json`.

`data/replays/catalog.jsonl` is the navigable index for replay and comparison folders. It prepares the UI and operators to select known artifacts without manually typing paths.

## Results

`data/results/` contains result collection outputs and overrides that may be needed by settlement flows. Result files are classified conservatively because an output can affect settlement even when it looks small.

Debug result captures under paths such as `data/results/_debug/` are runtime/debug artifacts, not product sources of truth.

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

