from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from vcbet.core.temporal_contract import file_md5, snapshot_time_from_dataframe, temporal_contract_status

ROOT = Path.cwd()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_source_run(source_run_dir: Path) -> dict[str, Any]:
    manifest = _load_json(source_run_dir / "run_manifest.json")
    quality_report = _load_json(source_run_dir / "quality_report.json")
    provenance = quality_report.get("provenance", {}) if isinstance(quality_report.get("provenance", {}), dict) else {}
    strategy_config = quality_report.get("strategy_config", {}) if isinstance(quality_report.get("strategy_config", {}), dict) else {}

    def _trace_value(*keys: str) -> str | None:
        for key in keys:
            value = manifest.get(key)
            if value:
                return str(value)
            value = provenance.get(key)
            if value:
                return str(value)
            value = strategy_config.get(key)
            if value:
                return str(value)
            value = quality_report.get(key)
            if value:
                return str(value)
        return None

    def _from_manifest(*keys: str) -> tuple[Path | None, str]:
        value = manifest
        for key in keys:
            if not isinstance(value, dict):
                return None, ""
            value = value.get(key)
        if not value:
            return None, ""
        path = Path(str(value))
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        return path, ".".join(keys)

    def _resolve_snapshot(filename: str, *manifest_keys: tuple[str, ...]) -> tuple[Path, str, str]:
        local = source_run_dir / filename
        if local.exists():
            return local, "frozen_run_local", filename
        for keys in manifest_keys:
            candidate, source_key = _from_manifest(*keys)
            if candidate and candidate.exists():
                return candidate, "manifest_reference", source_key
        return local, "missing", ""

    def _snapshot_time(path: Path, *manifest_keys: str) -> str | None:
        for key in manifest_keys:
            value = manifest.get(key)
            if value:
                return str(value)
        provenance = manifest.get("provenance", {})
        if isinstance(provenance, dict):
            for key in manifest_keys:
                value = provenance.get(key)
                if value:
                    return str(value)
        if path.exists():
            try:
                return snapshot_time_from_dataframe(pd.read_csv(path, sep=";"))
            except Exception:
                return None
        return None

    odds_path, odds_source_mode, odds_source_key = _resolve_snapshot(
        "odds_snapshot.csv",
        ("source_files", "odds_file"),
        ("odds_snapshot_file",),
    )
    xg_path, xg_source_mode, xg_source_key = _resolve_snapshot(
        "xg_snapshot.csv",
        ("source_files", "xg_file"),
        ("xg_snapshot_file",),
    )

    picks_path = source_run_dir / "picks_snapshot.csv"
    picks_source_mode = "frozen_run_local" if picks_path.exists() else "missing"
    picks_source_key = "picks_snapshot.csv" if picks_path.exists() else ""
    if not picks_path.exists():
        picks_candidate, picks_manifest_key = _from_manifest("picks_file")
        if picks_candidate and picks_candidate.exists():
            picks_path = picks_candidate
            picks_source_mode = "manifest_reference"
            picks_source_key = picks_manifest_key

    target_date = manifest.get("target_date") or source_run_dir.parent.name
    run_id = manifest.get("run_id") or source_run_dir.name
    if not Path(odds_path).exists():
        raise FileNotFoundError(f"odds_snapshot não encontrado para {source_run_dir}")
    if not Path(xg_path).exists():
        raise FileNotFoundError(f"xg_snapshot não encontrado para {source_run_dir}")

    odds_snapshot_time = _snapshot_time(Path(odds_path), "odds_snapshot_time")
    xg_asof = _snapshot_time(Path(xg_path), "xg_asof")
    decision_timestamp = _trace_value("decision_timestamp", "generated_at")
    temporal_status = _trace_value("temporal_contract_status") or temporal_contract_status(
        decision_timestamp=decision_timestamp,
        odds_snapshot_time=odds_snapshot_time,
        xg_asof=xg_asof,
    )
    config_trace = {
        "config_name": _trace_value("config_name", "strategy_config_name", "name"),
        "config_fingerprint": _trace_value("config_fingerprint", "strategy_config_fingerprint", "fingerprint"),
        "config_source_path": _trace_value("config_source_path", "source_path"),
        "config_snapshot_file": _trace_value("config_snapshot_file", "strategy_config_file", "snapshot_file"),
    }
    code_trace = {
        "signal_version": _trace_value("signal_version"),
        "pipeline_version": _trace_value("pipeline_version"),
    }
    missing_trace_fields = [
        key
        for key, value in {
            "decision_timestamp": decision_timestamp,
            "temporal_contract_status": temporal_status,
            "config_fingerprint": config_trace["config_fingerprint"],
            "config_snapshot_file": config_trace["config_snapshot_file"],
            "signal_version": code_trace["signal_version"],
            "pipeline_version": code_trace["pipeline_version"],
        }.items()
        if not value
    ]
    snapshot_modes = {
        "odds": odds_source_mode,
        "xg": xg_source_mode,
        "picks": picks_source_mode,
    }
    frozen_components = [name for name, mode in snapshot_modes.items() if mode == "frozen_run_local"]
    fallback_components = [name for name, mode in snapshot_modes.items() if mode == "manifest_reference"]
    missing_components = [name for name, mode in snapshot_modes.items() if mode == "missing"]
    replay_source_strength = "strong_frozen_inputs" if odds_source_mode == "frozen_run_local" and xg_source_mode == "frozen_run_local" else "partial_fallback_inputs"
    trace_complete = not missing_trace_fields and not missing_components and temporal_status == "complete"
    if replay_source_strength == "strong_frozen_inputs" and trace_complete:
        replay_quality_status = "strong_frozen_traceable"
    elif replay_source_strength == "strong_frozen_inputs":
        replay_quality_status = "strong_frozen_inputs_trace_incomplete"
    elif trace_complete:
        replay_quality_status = "partial_fallback_traceable"
    else:
        replay_quality_status = "partial_fallback_trace_incomplete"
    replay_limitations = []
    if fallback_components:
        replay_limitations.append("uses_manifest_reference_fallback_inputs")
    if missing_components:
        replay_limitations.append("missing_replay_input_components")
    if missing_trace_fields:
        replay_limitations.append("missing_historical_trace_fields")
    if temporal_status != "complete":
        replay_limitations.append("temporal_contract_not_complete")

    return {
        "manifest": manifest,
        "odds_path": Path(odds_path),
        "xg_path": Path(xg_path),
        "picks_path": Path(picks_path),
        "target_date": str(target_date),
        "run_id": str(run_id),
        "replay_input_contract": {
            "odds_source_mode": odds_source_mode,
            "xg_source_mode": xg_source_mode,
            "picks_source_mode": picks_source_mode,
            "odds_source_key": odds_source_key,
            "xg_source_key": xg_source_key,
            "picks_source_key": picks_source_key,
            "odds_path": str(odds_path),
            "xg_path": str(xg_path),
            "picks_path": str(picks_path),
            "odds_snapshot_hash": file_md5(odds_path) if Path(odds_path).exists() else None,
            "xg_snapshot_hash": file_md5(xg_path) if Path(xg_path).exists() else None,
            "odds_snapshot_time": odds_snapshot_time,
            "xg_asof": xg_asof,
            "source_strength": "strong" if odds_source_mode == "frozen_run_local" and xg_source_mode == "frozen_run_local" else "weak_fallback",
            "replay_source_strength": replay_source_strength,
            "replay_quality_status": replay_quality_status,
            "temporal_contract_status": temporal_status,
            "temporal_contract_strength": "complete" if temporal_status == "complete" else "incomplete",
            "component_source_modes": snapshot_modes,
            "frozen_components": frozen_components,
            "fallback_components": fallback_components,
            "missing_components": missing_components,
            "config_trace": config_trace,
            "code_trace": code_trace,
            "missing_trace_fields": missing_trace_fields,
            "replay_limitations": replay_limitations,
        },
    }

