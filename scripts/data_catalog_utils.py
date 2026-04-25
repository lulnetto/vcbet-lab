from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CATALOG_VERSION = 1
OFFICIAL_LEDGER = "data/history/bets_ledger.csv"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def relpath(path: Path | str, root: Path | None = None) -> str | None:
    if path is None:
        return None
    root = root or project_root()
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def path_from_manifest(value: Any, run_dir: Path, root: Path | None = None) -> str | None:
    if not value:
        return None
    root = root or project_root()
    p = Path(str(value))
    if p.is_absolute():
        return relpath(p, root)
    if p.exists():
        return relpath(p, root)
    candidate = run_dir / p
    if candidate.exists():
        return relpath(candidate, root)
    return relpath(root / p, root)


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "invalid_json"
    if not isinstance(data, dict):
        return {}, "invalid_shape"
    return data, "ok"


def manifest_quality(
    manifest: dict[str, Any], read_status: str, recommended_fields: list[str]
) -> str:
    if read_status != "ok":
        return read_status
    present = sum(1 for field in recommended_fields if manifest.get(field) not in (None, ""))
    if present == len(recommended_fields):
        return "complete"
    if present >= max(1, len(recommended_fields) // 2):
        return "partial"
    return "minimal"


def first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def infer_target_date(path: Path, manifest: dict[str, Any]) -> str | None:
    value = first_value(manifest, "target_date", "date", "run_date", "replay_date")
    if value:
        return str(value)
    for part in path.parts:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", part):
            return part
    match = re.search(r"(20\d{6})", path.name)
    if match:
        raw = match.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def infer_created_at(path: Path, manifest: dict[str, Any]) -> str | None:
    value = first_value(manifest, "created_at", "started_at", "generated_at")
    if value:
        return str(value)
    match = re.search(r"(20\d{6})_(\d{6})", path.name)
    if match:
        day, clock = match.groups()
        return (
            f"{day[:4]}-{day[4:6]}-{day[6:]} "
            f"{clock[:2]}:{clock[2:4]}:{clock[4:]}"
        )
    return None


def infer_mode(path: Path, manifest: dict[str, Any], *, is_replay: bool = False) -> str:
    explicit = first_value(manifest, "run_mode", "mode", "replay_mode")
    if explicit:
        return str(explicit)
    haystack = path.as_posix().lower()
    ledger = str(first_value(manifest, "ledger_file") or "").lower()
    if is_replay or "/replays/" in haystack:
        return "replay"
    if "debug" in haystack or "tmp" in haystack or "temporary" in haystack:
        return "debug"
    if any(marker in haystack for marker in ("test", "sandbox", "rerun", "experiment")):
        return "sandbox"
    if ledger and OFFICIAL_LEDGER in ledger and not any(
        marker in haystack for marker in ("test", "sandbox", "rerun", "debug")
    ):
        return "official"
    return "unknown"


def existing_child(run_dir: Path, *names: str) -> str | None:
    for name in names:
        candidate = run_dir / name
        if candidate.exists():
            return relpath(candidate)
    return None


def source_run_dir_from_ref(value: Any, root: Path | None = None) -> str | None:
    if not value:
        return None
    root = root or project_root()
    text = str(value)
    match = re.search(r"(?:^|[|:])(/?.*?data/runs/\d{4}-\d{2}-\d{2}/[^|]+)", text)
    if not match:
        return None
    raw = match.group(1)
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    path = Path(raw)
    if path.suffix:
        path = path.parent
    return relpath(path, root)


def jsonl_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                json.loads(line)
    return True
