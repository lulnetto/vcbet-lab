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
    source_run_dir_from_ref,
)


RECOMMENDED_FIELDS = [
    "status",
    "updated_at",
    "config_name",
    "picks_file",
    "ledger_file",
]


def replay_dirs(root: Path) -> list[Path]:
    base = root / "data" / "replays"
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


def comparison_summary(replay_dir: Path, root: Path) -> str | None:
    return existing_child(replay_dir, "replay_result.json", "comparison_summary.json", "comparison_summary.csv")


def replay_strength(replay_id: str, manifest: dict[str, object]) -> str | None:
    explicit = first_value(manifest, "replay_strength", "strategy_strength")
    if explicit:
        return str(explicit)
    lower = replay_id.lower()
    for marker in ("champion_strict", "intermediate_balanced", "legacy_recovered", "legacy_v2"):
        if marker in lower:
            return marker
    if replay_id.startswith("comparison_"):
        return "comparison"
    return None


def configs(replay_id: str, manifest: dict[str, object]) -> list[str]:
    value = first_value(manifest, "configs", "config_name", "strategy_config_name")
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    lower = replay_id.lower()
    return [name for name in ("champion_strict", "intermediate_balanced", "legacy_recovered", "legacy_v2") if name in lower]


def build_record(replay_dir: Path, root: Path) -> dict[str, object]:
    manifest_file = replay_dir / "run_manifest.json"
    manifest, read_status = read_json(manifest_file)
    summary_file = comparison_summary(replay_dir, root)
    replay_id = str(
        first_value(manifest, "replay_id", "run_id", "source_run_id") or replay_dir.name
    )
    quality = manifest_quality(manifest, read_status, RECOMMENDED_FIELDS)
    source_run_dir = first_value(manifest, "source_run_dir")
    if source_run_dir:
        source_run_dir = path_from_manifest(source_run_dir, replay_dir, root)
    else:
        source_run_dir = source_run_dir_from_ref(first_value(manifest, "source_snapshot_ref"), root)
    return {
        "catalog_version": CATALOG_VERSION,
        "replay_id": replay_id,
        "replay_dir": relpath(replay_dir, root),
        "replay_mode": infer_mode(replay_dir, manifest, is_replay=True),
        "target_date": infer_target_date(replay_dir, manifest),
        "created_at": infer_created_at(replay_dir, manifest),
        "updated_at": first_value(manifest, "updated_at", "completed_at"),
        "status": first_value(manifest, "status") or ("summary_only" if summary_file else "unknown"),
        "configs": configs(replay_id, manifest),
        "source_run_dir": source_run_dir,
        "summary_file": summary_file,
        "manifest_file": relpath(manifest_file, root) if manifest_file.exists() else None,
        "replay_strength": replay_strength(replay_id, manifest),
        "manifest_schema_quality": quality,
    }


def sort_key(record: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(record.get("created_at") or ""),
        str(record.get("target_date") or ""),
        str(record.get("replay_id") or ""),
    )


def main() -> int:
    root = project_root()
    records = [build_record(path, root) for path in replay_dirs(root)]
    records.sort(key=sort_key, reverse=True)
    output = root / "data" / "replays" / "catalog.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {len(records)} replay catalog records to {relpath(output, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
