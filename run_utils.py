from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

DEFAULT_BASE_OUTPUT_DIR = Path("data") / "runs"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def generate_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def resolve_target_date(target_date: str | None = None) -> str:
    if target_date:
        return target_date
    return datetime.now().strftime("%Y-%m-%d")


def get_run_dir(
    run_id: str,
    target_date: str | None = None,
    base_output_dir: str | Path | None = None,
) -> Path:
    target_date = resolve_target_date(target_date)
    base_dir = Path(base_output_dir) if base_output_dir else DEFAULT_BASE_OUTPUT_DIR
    return base_dir / target_date / run_id


def ensure_run_dir(
    run_id: str,
    target_date: str | None = None,
    base_output_dir: str | Path | None = None,
) -> Path:
    run_dir = get_run_dir(run_id=run_id, target_date=target_date, base_output_dir=base_output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def build_manifest(
    run_id: str,
    target_date: str,
    run_dir: str | Path,
    **extra: Any,
) -> Dict[str, Any]:
    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "target_date": target_date,
        "created_at": now_str(),
        "run_dir": str(run_dir),
        "status": "initialized",
    }
    manifest.update(extra)
    return manifest


def manifest_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / "run_manifest.json"


def save_manifest(run_dir: str | Path, manifest: Dict[str, Any]) -> Path:
    path = manifest_path(run_dir)
    with path.open("w", encoding="utf-8") as arquivo:
        json.dump(manifest, arquivo, ensure_ascii=False, indent=2)
    return path


def load_manifest(run_dir: str | Path) -> Dict[str, Any]:
    path = manifest_path(run_dir)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def update_manifest(run_dir: str | Path, **updates: Any) -> Dict[str, Any]:
    manifest = load_manifest(run_dir)
    manifest.update(updates)
    manifest.setdefault("updated_at", now_str())
    manifest["updated_at"] = now_str()
    save_manifest(run_dir, manifest)
    return manifest
