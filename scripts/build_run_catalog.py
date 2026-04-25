#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from data_catalog_utils import (
    CATALOG_VERSION,
    existing_child,
    first_value,
    infer_created_at,
    infer_mode,
    infer_target_date,
    manifest_quality,
    path_from_manifest,
    project_root,
    read_json,
    relpath,
)


RECOMMENDED_FIELDS = [
    "run_id",
    "target_date",
    "created_at",
    "updated_at",
    "status",
    "picks_file",
    "picks_rows",
]


def run_dirs(root: Path) -> list[Path]:
    base = root / "data" / "runs"
    if not base.exists():
        return []
    dirs: list[Path] = []
    for day_dir in base.iterdir():
        if not day_dir.is_dir() or day_dir.name.startswith("."):
            continue
        for candidate in day_dir.iterdir():
            if candidate.is_dir() and not candidate.name.startswith("."):
                dirs.append(candidate)
    return dirs


def build_record(run_dir: Path, root: Path) -> dict[str, object]:
    manifest_file = run_dir / "run_manifest.json"
    manifest, read_status = read_json(manifest_file)
    run_id = str(first_value(manifest, "run_id", "source_run_id") or run_dir.name)
    quality = manifest_quality(manifest, read_status, RECOMMENDED_FIELDS)
    return {
        "catalog_version": CATALOG_VERSION,
        "run_id": run_id,
        "run_dir": relpath(run_dir, root),
        "run_mode": infer_mode(run_dir, manifest),
        "target_date": infer_target_date(run_dir, manifest),
        "created_at": infer_created_at(run_dir, manifest),
        "updated_at": first_value(manifest, "updated_at", "completed_at"),
        "status": first_value(manifest, "status") or "unknown",
        "config_name": first_value(manifest, "config_name", "strategy_config_name"),
        "config_fingerprint": first_value(
            manifest, "config_fingerprint", "strategy_config_fingerprint"
        ),
        "ledger_file": path_from_manifest(manifest.get("ledger_file"), run_dir, root),
        "picks_file": path_from_manifest(
            first_value(manifest, "picks_file") or existing_child(run_dir, "picks_snapshot.csv", "entradas_kelly.csv"),
            run_dir,
            root,
        ),
        "picks_rows": first_value(manifest, "picks_rows"),
        "alias_pending_rows": first_value(manifest, "alias_pending_rows"),
        "quality_report_file": path_from_manifest(
            first_value(manifest, "quality_report_file") or existing_child(run_dir, "quality_report.json"),
            run_dir,
            root,
        ),
        "temporal_contract_status": first_value(manifest, "temporal_contract_status"),
        "pipeline_version": first_value(manifest, "pipeline_version", "signal_version"),
        "manifest_file": relpath(manifest_file, root) if manifest_file.exists() else None,
        "manifest_schema_quality": quality,
    }


def sort_key(record: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(record.get("created_at") or ""),
        str(record.get("target_date") or ""),
        str(record.get("run_id") or ""),
    )


def main() -> int:
    root = project_root()
    records = [build_record(path, root) for path in run_dirs(root)]
    records.sort(key=sort_key, reverse=True)
    output = root / "data" / "runs" / "catalog.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {len(records)} run catalog records to {relpath(output, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
