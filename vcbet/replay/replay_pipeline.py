from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from vcbet.core.ledger_manager import normalize_ledger_schema
from vcbet.core.strategy_config import CONFIGS_DIR, ConfigResolutionError, list_available_configs, resolve_config_file
from vcbet.core.temporal_contract import file_md5, snapshot_time_from_dataframe, temporal_contract_status
from vcbet.paths import REPLAYS_DIR

DEFAULT_REPLAY_DIR = REPLAYS_DIR
ROOT = Path.cwd()
MANUAL_DEFAULT_BASELINE_CONFIG = "legacy_v2"
MANUAL_CONSERVATIVE_REFERENCE_CONFIG = "champion_strict"
RECOMMENDATION_METHOD = "manual_policy"
CONFIG_ROLE_POLICY = {
    MANUAL_DEFAULT_BASELINE_CONFIG: "default_baseline",
    MANUAL_CONSERVATIVE_REFERENCE_CONFIG: "conservative_reference",
    "intermediate_balanced": "secondary_candidate",
    "legacy_recovered": "deprecated_reference",
}
CONFIG_ROLE_NOTES = {
    "default_baseline": "Manual policy baseline for future replay comparisons; verify against the scorecard metrics before changing production behavior.",
    "conservative_reference": "Manual policy restrictive reference for risk-controlled comparison, not a metric-ranked best config.",
    "secondary_candidate": "Keep available for challenger analysis, but do not treat as the primary baseline by default.",
    "deprecated_reference": "Historical recovery preset; useful for archaeology, not a primary candidate for future analysis.",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sorted_counter_dict(values: pd.Series) -> dict[str, int]:
    counter = Counter(values.fillna("missing").astype(str))
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _normalize_signature(df: pd.DataFrame) -> pd.Series:
    line = df.get("line", pd.Series([pd.NA] * len(df)))
    line_text = line.apply(lambda v: "" if pd.isna(v) else f"{float(v):.2f}")
    return (
        df.get("match_name", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("market_type", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("selection_raw", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + line_text.astype(str)
    )




def _normalize_family_signature(df: pd.DataFrame) -> pd.Series:
    return (
        df.get("match_name", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("market_type", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("side", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("target_team_role", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("target_team_name", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
    )


def _asian_total_line_drift(reference_df: pd.DataFrame, candidate_df: pd.DataFrame) -> dict[str, Any]:
    ref = reference_df.loc[reference_df.get("market_type", pd.Series(dtype=object)).eq("asian_total")].copy()
    cand = candidate_df.loc[candidate_df.get("market_type", pd.Series(dtype=object)).eq("asian_total")].copy()
    if ref.empty or cand.empty:
        return {
            "shifted_line_matches_total": 0,
            "delta_counts": {},
            "examples": [],
        }

    ref["family_sig"] = _normalize_family_signature(ref)
    cand["family_sig"] = _normalize_family_signature(cand)
    ref["line_num"] = pd.to_numeric(ref.get("line"), errors="coerce")
    cand["line_num"] = pd.to_numeric(cand.get("line"), errors="coerce")
    delta_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for _, row in ref.iterrows():
        if pd.isna(row["line_num"]):
            continue
        family = cand.loc[cand["family_sig"] == row["family_sig"]].copy()
        if family.empty:
            continue
        exact = family.loc[(family["selection_raw"].astype(str).str.lower() == str(row.get("selection_raw", "")).lower()) & (family["line_num"] == row["line_num"])]
        if not exact.empty:
            continue
        family = family.dropna(subset=["line_num"])
        if family.empty:
            continue
        family["line_delta"] = (family["line_num"] - float(row["line_num"])).abs()
        best = family.sort_values(["line_delta", "confidence_score", "ev_percent"], ascending=[True, False, False]).iloc[0]
        delta = round(float(best["line_num"]) - float(row["line_num"]), 2)
        if abs(delta) > 1.0:
            continue
        delta_counts[f"{delta:+.2f}"] += 1
        if len(examples) < 20:
            examples.append({
                "match_name": row.get("match_name"),
                "reference_selection": row.get("selection_raw"),
                "reference_line": float(row["line_num"]),
                "candidate_selection": best.get("selection_raw"),
                "candidate_line": float(best["line_num"]),
                "delta": delta,
            })

    return {
        "shifted_line_matches_total": int(sum(delta_counts.values())),
        "delta_counts": dict(sorted(delta_counts.items())),
        "examples": examples,
    }

def _compare_pick_sets(reference_df: pd.DataFrame, candidate_df: pd.DataFrame) -> dict[str, Any]:
    if reference_df.empty and candidate_df.empty:
        return {
            "reference_total": 0,
            "candidate_total": 0,
            "overlap": 0,
            "precision": 0.0,
            "recall": 0.0,
            "jaccard": 0.0,
            "missing_from_candidate": [],
            "extra_in_candidate": [],
        }

    ref_sig = set(_normalize_signature(reference_df).tolist())
    cand_sig = set(_normalize_signature(candidate_df).tolist())
    overlap = ref_sig & cand_sig
    missing = sorted(ref_sig - cand_sig)
    extra = sorted(cand_sig - ref_sig)
    precision = len(overlap) / len(cand_sig) if cand_sig else 0.0
    recall = len(overlap) / len(ref_sig) if ref_sig else 0.0
    union = len(ref_sig | cand_sig)
    jaccard = len(overlap) / union if union else 0.0
    return {
        "reference_total": len(ref_sig),
        "candidate_total": len(cand_sig),
        "overlap": len(overlap),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "jaccard": round(jaccard * 100, 2),
        "missing_from_candidate": missing[:50],
        "extra_in_candidate": extra[:50],
    }


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


def _load_picks_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep=";")


def _load_csv_semicolon(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep=";")


def _load_ledger_csv(path: Path) -> pd.DataFrame:
    df = _load_csv_semicolon(path)
    return normalize_ledger_schema(df) if not df.empty else df


def _summarize_replay_ledger(ledger_file: Path) -> dict[str, Any]:
    df = _load_ledger_csv(ledger_file)
    if df.empty:
        return {
            "total": 0,
            "settled": 0,
            "open": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "model_units": 0.0,
            "model_roi_percent": 0.0,
        }

    bet_status = df.get("final_bet_status", pd.Series(["open"] * len(df))).fillna("open").astype(str).str.lower()
    settlement_status = df.get("final_settlement_status", pd.Series(["pending"] * len(df))).fillna("pending").astype(str).str.lower()
    result_units = pd.to_numeric(df.get("result_units_model", pd.Series([0] * len(df))), errors="coerce").fillna(0.0)
    stake = pd.to_numeric(df.get("stake_units", pd.Series([0] * len(df))), errors="coerce").fillna(0.0)
    settled_mask = bet_status.isin({"settled", "voided", "cancelled"}) | settlement_status.isin({"win", "loss", "half_win", "half_loss", "push", "void"})

    settled_stake = float(stake[settled_mask].sum())
    model_units = float(result_units[settled_mask].sum())
    roi = (model_units / settled_stake * 100.0) if settled_stake else 0.0

    return {
        "total": int(len(df)),
        "settled": int(settled_mask.sum()),
        "open": int((~settled_mask).sum()),
        "wins": int(settlement_status.eq("win").sum()),
        "losses": int(settlement_status.eq("loss").sum()),
        "half_wins": int(settlement_status.eq("half_win").sum()),
        "half_losses": int(settlement_status.eq("half_loss").sum()),
        "pushes": int(settlement_status.eq("push").sum()),
        "voided": int(settlement_status.eq("void").sum()),
        "postponed": int(bet_status.eq("postponed").sum()),
        "model_units": round(model_units, 3),
        "model_roi_percent": round(roi, 2),
    }


def _config_role(config_name: str) -> str:
    return CONFIG_ROLE_POLICY.get(config_name, "secondary_candidate")


def _model_result_summary(item: dict[str, Any]) -> dict[str, Any]:
    settlement = (item.get("settlement") or {}).get("settlement_summary") or {}
    return {
        "available": bool(item.get("settlement")),
        "settled": int(settlement.get("settled", 0) or 0),
        "open": int(settlement.get("open", 0) or 0),
        "wins": int(settlement.get("wins", 0) or 0),
        "losses": int(settlement.get("losses", 0) or 0),
        "pushes": int(settlement.get("pushes", 0) or 0),
        "model_units": float(settlement.get("model_units", 0.0) or 0.0),
        "model_roi_percent": float(settlement.get("model_roi_percent", 0.0) or 0.0),
        "interpretation_note": "Replay settlement uses model stake/payoff accounting; it is not proof of calibrated profitability.",
    }


def _build_config_scorecard(item: dict[str, Any]) -> dict[str, Any]:
    config_name = str(item.get("config_name") or "")
    comp = item.get("comparison") or {}
    role = _config_role(config_name)
    quality_processing = item.get("quality_processing") or {}
    discard_counts = quality_processing.get("discard_reason_counts") or {}
    return {
        "config_name": config_name,
        "role": role,
        "role_source": RECOMMENDATION_METHOD,
        "is_default_baseline": config_name == MANUAL_DEFAULT_BASELINE_CONFIG,
        "is_conservative_reference": config_name == MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
        "primary_candidate_status": "primary" if config_name == MANUAL_DEFAULT_BASELINE_CONFIG else ("reference" if config_name == MANUAL_CONSERVATIVE_REFERENCE_CONFIG else "secondary"),
        "role_note": CONFIG_ROLE_NOTES.get(role, CONFIG_ROLE_NOTES["secondary_candidate"]),
        "return_code": int(item.get("return_code", 0) or 0),
        "picks_total": int(item.get("picks_total", 0) or 0),
        "source_picks_total": int(comp.get("reference_total", 0) or 0),
        "overlap_with_source": int(comp.get("overlap", 0) or 0),
        "precision_percent": float(comp.get("precision", 0.0) or 0.0),
        "recall_percent": float(comp.get("recall", 0.0) or 0.0),
        "jaccard_percent": float(comp.get("jaccard", 0.0) or 0.0),
        "picks_by_market": item.get("picks_by_market") or {},
        "picks_by_league": item.get("picks_by_league") or {},
        "asian_total_shifted_lines": int((item.get("asian_total_line_drift") or {}).get("shifted_line_matches_total", 0) or 0),
        "quality_discards": {
            "edge_below_min": int(discard_counts.get("pick_filter_edge_below_min", 0) or 0),
            "odd_out_of_range": int(discard_counts.get("pick_filter_odd_out_of_range", 0) or 0),
            "total": int(sum(int(v or 0) for v in discard_counts.values())),
        },
        "model_result_summary": _model_result_summary(item),
        "evidence_note": "Scorecard compares replay output to source picks and optional replay settlement; it is not proof of calibrated edge.",
    }


def _build_comparison_context(scorecards: list[dict[str, Any]]) -> dict[str, Any]:
    deprecated = [s["config_name"] for s in scorecards if s.get("role") == "deprecated_reference"]
    secondary = [
        s["config_name"]
        for s in scorecards
        if s.get("role") == "secondary_candidate" and s["config_name"] not in {MANUAL_DEFAULT_BASELINE_CONFIG, MANUAL_CONSERVATIVE_REFERENCE_CONFIG}
    ]
    return {
        "default_baseline_config": MANUAL_DEFAULT_BASELINE_CONFIG,
        "conservative_reference_config": MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
        "recommendation_method": RECOMMENDATION_METHOD,
        "recommendation_basis": "manual policy labels maintained separately from replay scorecard evidence",
        "metric_ranking_applied": False,
        "too_close_to_call": None,
        "secondary_candidate_configs": secondary,
        "deprecated_reference_configs": deprecated,
        "basis": "Replay pick-set comparison with explicit replay-quality and source-strength fields, plus optional model-result settlement summary.",
        "profitability_caveat": "Replay/model metrics are operational evidence only; recommendations are not proof of calibrated profitability or metric-ranked superiority.",
    }


def _run_replay_settlement(
    *,
    replay_dir: Path,
    ledger_file: Path,
    python_bin: str,
    results_source: str,
    results_grace_minutes: int,
    results_max_pages: int,
    results_debug: bool,
) -> dict[str, Any]:
    results_file = replay_dir / "results_auto.csv"
    debug_dir = replay_dir / "results_debug"

    results_cmd = [
        python_bin,
        "-m",
        "vcbet.collectors.results_collector",
        "--ledger-file", str(ledger_file),
        "--output-file", str(results_file),
        "--all-pending",
        "--grace-minutes", str(results_grace_minutes),
        "--debug-dir", str(debug_dir),
        "--max-pages", str(results_max_pages),
        "--source", results_source,
    ]
    if results_debug:
        results_cmd.append("--debug")

    settlement_cmd = [
        python_bin,
        "-m",
        "vcbet.settlement.settlement_engine",
        "--ledger-file", str(ledger_file),
        "--results-file", str(results_file),
    ]

    results_proc = subprocess.run(results_cmd, cwd=Path.cwd(), capture_output=True, text=True)
    settlement_proc = subprocess.run(settlement_cmd, cwd=Path.cwd(), capture_output=True, text=True) if results_proc.returncode == 0 else None

    return {
        "results_file": str(results_file),
        "results_return_code": results_proc.returncode,
        "results_stdout_tail": results_proc.stdout.splitlines()[-50:],
        "results_stderr_tail": results_proc.stderr.splitlines()[-30:],
        "settlement_return_code": settlement_proc.returncode if settlement_proc else None,
        "settlement_stdout_tail": settlement_proc.stdout.splitlines()[-50:] if settlement_proc else [],
        "settlement_stderr_tail": settlement_proc.stderr.splitlines()[-30:] if settlement_proc else [],
        "settlement_summary": _summarize_replay_ledger(ledger_file),
    }



def _compact_picks_for_summary(picks_df: pd.DataFrame, ledger_file: Path, limit: int = 200) -> list[dict[str, Any]]:
    source_df = _load_ledger_csv(ledger_file) if ledger_file.exists() else picks_df
    if source_df.empty:
        return []
    wanted = [
        "league", "match_name", "market_type", "selection_raw", "target_team_name",
        "line", "odd_entrada", "odd_justa", "ev_percent", "confidence_score",
        "stake_units", "run_id", "config_name", "config_fingerprint", "source_run_id",
        "odds_source_run_id", "xg_source_run_id", "odds_snapshot_hash", "xg_snapshot_hash",
        "odds_snapshot_time", "xg_asof", "temporal_contract_version", "temporal_contract_status",
        "decision_timestamp", "pick_safety_status", "candidate_stage", "safety_gate_reason",
        "decision_policy_status", "decision_reject_reason", "selection_policy_status", "selection_reject_reason",
        "portfolio_risk_status", "portfolio_risk_reason", "portfolio_exposure_scope", "portfolio_exposure_after", "market_family",
        "final_bet_status", "result_units_model", "risk_flags",
    ]
    rows: list[dict[str, Any]] = []
    for _, row in source_df.head(limit).iterrows():
        item: dict[str, Any] = {}
        for col in wanted:
            value = row.get(col, None)
            if pd.isna(value):
                value = None
            if hasattr(value, "item"):
                value = value.item()
            item[col] = value
        rows.append(item)
    return rows


def _run_single_replay(
    *,
    source_info: dict[str, Any],
    config_ref: str,
    output_root: Path,
    alias_file: str,
    python_bin: str,
    evaluate_results: bool = False,
    results_source: str = "auto",
    results_grace_minutes: int = 110,
    results_max_pages: int = 6,
    results_debug: bool = False,
) -> dict[str, Any]:
    possible_path = Path(config_ref)
    if possible_path.exists():
        config_path = resolve_config_file(config_file=possible_path, strict=True)
    else:
        config_path = resolve_config_file(config_name=config_ref, strict=True)
    config_name = Path(config_path).stem if config_path else config_ref
    replay_run_id = f"replay_{source_info['run_id']}_{config_name}"
    replay_target_date = str(source_info["target_date"])
    replay_dir = output_root / replay_target_date / replay_run_id
    replay_dir.mkdir(parents=True, exist_ok=True)
    ledger_file = replay_dir / "replay_ledger.csv"

    cmd = [
        python_bin,
        "-m",
        "vcbet.core.pipeline_ev",
        "--run-id", replay_run_id,
        "--odds-file", str(source_info["odds_path"]),
        "--xg-file", str(source_info["xg_path"]),
        "--alias-file", alias_file,
        "--ledger-file", str(ledger_file),
        "--output-dir", str(output_root),
    ]
    if config_path:
        cmd += ["--config-file", str(config_path)]
    else:
        cmd += ["--config-name", config_ref]

    result = subprocess.run(
        cmd,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )

    replay_picks = replay_dir / "picks_snapshot.csv"
    candidate_df = _load_picks_csv(replay_picks)
    reference_df = _load_picks_csv(Path(source_info["picks_path"]))
    comparison = _compare_pick_sets(reference_df, candidate_df)
    asian_total_line_drift = _asian_total_line_drift(reference_df, candidate_df)

    settlement_payload = None
    if evaluate_results and result.returncode == 0:
        settlement_payload = _run_replay_settlement(
            replay_dir=replay_dir,
            ledger_file=ledger_file,
            python_bin=python_bin,
            results_source=results_source,
            results_grace_minutes=results_grace_minutes,
            results_max_pages=results_max_pages,
            results_debug=results_debug,
        )

    quality_report = _load_json(replay_dir / "quality_report.json")
    payload = {
        "config_name": config_name,
        "config_path": str(config_path) if config_path else config_ref,
        "run_id": replay_run_id,
        "return_code": result.returncode,
        "stdout_tail": result.stdout.splitlines()[-80:],
        "stderr_tail": result.stderr.splitlines()[-40:],
        "picks_total": int(len(candidate_df)),
        "picks_by_market": _sorted_counter_dict(candidate_df.get("market_type", pd.Series(dtype=object))),
        "picks_by_league": _sorted_counter_dict(candidate_df.get("league", pd.Series(dtype=object))),
        "picks_preview": _compact_picks_for_summary(candidate_df, ledger_file),
        "picks_file": str(replay_picks) if replay_picks.exists() else None,
        "ledger_file": str(ledger_file) if ledger_file.exists() else None,
        "comparison": comparison,
        "asian_total_line_drift": asian_total_line_drift,
        "quality_report_file": str(replay_dir / "quality_report.json") if (replay_dir / "quality_report.json").exists() else None,
        "quality_processing": quality_report.get("processing", {}),
        "quality_outputs": quality_report.get("outputs", {}),
        "replay_dir": str(replay_dir),
        "replay_input_contract": source_info.get("replay_input_contract", {}),
        "settlement": settlement_payload,
    }
    payload["scorecard"] = _build_config_scorecard(payload)
    (replay_dir / "replay_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def replay_configs_for_run(
    *,
    source_run_dir: Path,
    config_refs: list[str],
    output_dir: Path,
    alias_file: str,
    python_bin: str,
    evaluate_results: bool = False,
    results_source: str = "auto",
    results_grace_minutes: int = 110,
    results_max_pages: int = 6,
    results_debug: bool = False,
) -> Path:
    source_info = _resolve_source_run(source_run_dir)
    comparison_dir = output_dir / str(source_info["target_date"]) / f"comparison_{source_info['run_id']}"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for config_ref in config_refs:
        results.append(
            _run_single_replay(
                source_info=source_info,
                config_ref=config_ref,
                output_root=output_dir,
                alias_file=alias_file,
                python_bin=python_bin,
                evaluate_results=evaluate_results,
                results_source=results_source,
                results_grace_minutes=results_grace_minutes,
                results_max_pages=results_max_pages,
                results_debug=results_debug,
            )
        )

    scorecards = [_build_config_scorecard(item) for item in results]
    for item, scorecard in zip(results, scorecards):
        item["scorecard"] = scorecard

    comparison_context = _build_comparison_context(scorecards)
    replay_input_contract = source_info.get("replay_input_contract", {})
    summary = {
        "source_run_dir": str(source_run_dir),
        "source_run_id": source_info["run_id"],
        "target_date": source_info["target_date"],
        "source_picks_file": str(source_info["picks_path"]),
        "replay_input_contract": replay_input_contract,
        "replay_quality_status": replay_input_contract.get("replay_quality_status"),
        "replay_source_strength": replay_input_contract.get("replay_source_strength"),
        "temporal_contract_status": replay_input_contract.get("temporal_contract_status"),
        "replay_limitations": replay_input_contract.get("replay_limitations", []),
        "comparison_context": comparison_context,
        "recommended_configs": {
            "method": RECOMMENDATION_METHOD,
            "basis": comparison_context["recommendation_basis"],
            "metric_ranking_applied": False,
            "default_baseline": MANUAL_DEFAULT_BASELINE_CONFIG,
            "conservative_reference": MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
            "secondary_or_deprecated": comparison_context["secondary_candidate_configs"] + comparison_context["deprecated_reference_configs"],
        },
        "config_scorecards": scorecards,
        "results": results,
        "available_configs": list_available_configs(),
    }
    summary_path = comparison_dir / "comparison_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for item in results:
        comp = item["comparison"]
        scorecard = item.get("scorecard") or _build_config_scorecard(item)
        rows.append({
            "config_name": item["config_name"],
            "role": scorecard["role"],
            "primary_candidate_status": scorecard["primary_candidate_status"],
            "is_default_baseline": scorecard["is_default_baseline"],
            "is_conservative_reference": scorecard["is_conservative_reference"],
            "picks_total": item["picks_total"],
            "return_code": item["return_code"],
            "overlap": comp["overlap"],
            "precision_percent": comp["precision"],
            "recall_percent": comp["recall"],
            "jaccard_percent": comp["jaccard"],
            "edge_below_min_discards": item["quality_processing"].get("discard_reason_counts", {}).get("pick_filter_edge_below_min", 0),
            "odd_out_of_range_discards": item["quality_processing"].get("discard_reason_counts", {}).get("pick_filter_odd_out_of_range", 0),
            "asian_total_shifted_lines": item.get("asian_total_line_drift", {}).get("shifted_line_matches_total", 0),
            "settled": (item.get("settlement") or {}).get("settlement_summary", {}).get("settled", 0),
            "model_units": (item.get("settlement") or {}).get("settlement_summary", {}).get("model_units", 0.0),
            "model_roi_percent": (item.get("settlement") or {}).get("settlement_summary", {}).get("model_roi_percent", 0.0),
            "replay_quality_status": replay_input_contract.get("replay_quality_status"),
            "replay_source_strength": replay_input_contract.get("replay_source_strength"),
            "temporal_contract_status": replay_input_contract.get("temporal_contract_status"),
        })
    pd.DataFrame(rows).sort_values(["jaccard_percent", "overlap", "picks_total"], ascending=[False, False, False]).to_csv(
        comparison_dir / "comparison_summary.csv",
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocessa snapshots históricos com configs versionadas para reconstruir baseline.")
    parser.add_argument("--source-run-dir", required=True, help="Diretório da run histórica original")
    parser.add_argument("--config", action="append", required=True, dest="configs", help="Preset em ./configs ou caminho para JSON. Pode repetir.")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPLAY_DIR), help="Diretório base para os replays")
    parser.add_argument("--alias-file", default="alias_times.json", help="Arquivo de aliases")
    parser.add_argument("--python-bin", default="python3", help="Binário Python")
    parser.add_argument("--evaluate-results", action="store_true", help="Após cada replay, coleta resultados e liquida o replay_ledger.")
    parser.add_argument("--results-source", default="auto", choices=["auto", "browser", "api"], help="Fonte usada na coleta de resultados do replay.")
    parser.add_argument("--results-grace-minutes", type=int, default=110, help="Grace period para coleta de resultados.")
    parser.add_argument("--results-max-pages", type=int, default=6, help="Páginas máximas na coleta de resultados.")
    parser.add_argument("--results-debug", action="store_true", help="Debug da coleta de resultados do replay.")
    args = parser.parse_args()

    summary_path = replay_configs_for_run(
        source_run_dir=Path(args.source_run_dir).resolve(),
        config_refs=args.configs,
        output_dir=Path(args.output_dir).resolve(),
        alias_file=args.alias_file,
        python_bin=args.python_bin,
        evaluate_results=args.evaluate_results,
        results_source=args.results_source,
        results_grace_minutes=args.results_grace_minutes,
        results_max_pages=args.results_max_pages,
        results_debug=args.results_debug,
    )
    print(f"[OK] Replay concluído. Resumo salvo em: {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except ConfigResolutionError as exc:
        raise SystemExit(f"[ERRO_CONFIG] {exc}")
