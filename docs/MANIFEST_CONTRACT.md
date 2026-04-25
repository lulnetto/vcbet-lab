# Manifest Contract

`run_manifest.json` already exists in current run and replay folders. Cycle 7 does not introduce a breaking manifest migration; it adds catalog builders that read existing manifests defensively.

## Compatibility Rule

Old runs must not break just because their manifest is partial. Missing fields should become `null`, safe defaults, or inferred values in catalogs. Historical manifests should be preserved as written.

## Recommended Run Manifest Fields

- `run_id`
- `target_date`
- `created_at`
- `updated_at`
- `status`
- `run_mode` or another explicit mode field when available
- `config_name`
- `config_fingerprint`
- `ledger_file`
- `picks_file`
- `picks_rows`
- `alias_pending_rows`
- `quality_report_file`
- `temporal_contract_status`
- `pipeline_version`

## Recommended Replay Manifest Fields

- `replay_id` or `run_id`
- `target_date`
- `created_at`
- `updated_at`
- `status`
- `replay_mode` or another explicit mode field when available
- `configs` or `config_name`
- `source_run_dir` or `source_snapshot_ref`
- `summary_file`
- `replay_strength`

## Catalog Fields

`data/runs/catalog.jsonl` contains one JSON object per run with:

- `catalog_version`
- `run_id`
- `run_dir`
- `run_mode`
- `target_date`
- `created_at`
- `updated_at`
- `status`
- `config_name`
- `config_fingerprint`
- `ledger_file`
- `picks_file`
- `picks_rows`
- `alias_pending_rows`
- `quality_report_file`
- `temporal_contract_status`
- `pipeline_version`
- `manifest_file`
- `manifest_schema_quality`

`data/replays/catalog.jsonl` contains one JSON object per replay or comparison with:

- `catalog_version`
- `replay_id`
- `replay_dir`
- `replay_mode`
- `target_date`
- `created_at`
- `updated_at`
- `status`
- `configs`
- `source_run_dir`
- `summary_file`
- `manifest_file`
- `replay_strength`
- `manifest_schema_quality`

## Manifest Schema Quality

- `complete`: all recommended fields for that catalog type are present.
- `partial`: enough recommended fields exist to make the manifest useful, but some are missing.
- `minimal`: the manifest is valid JSON but has only a small subset of recommended fields.
- `missing`: no manifest file exists for the artifact.
- `invalid_json`: the manifest file exists but cannot be parsed as JSON.
- `invalid_shape`: the manifest parses but is not a JSON object.

## Mode Inference

Catalog builders use explicit manifest mode fields first. If no explicit mode exists, they infer conservatively from path/name/ledger:

- `official` only when linked to `data/history/bets_ledger.csv` and not clearly test, rerun, sandbox, or debug.
- `sandbox` for test, sandbox, rerun, or experiment paths.
- `replay` for artifacts under `data/replays/`.
- `debug` for debug or temporary paths.
- `unknown` when inference would be speculative.

