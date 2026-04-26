from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from vcbet.core.ledger_manager import normalize_ledger_schema
from vcbet.core.strategy_config import resolve_config_file
from vcbet.replay.scoring import (
    _asian_total_line_drift,
    _build_config_scorecard,
    _compare_pick_sets,
    _sorted_counter_dict,
)
from vcbet.replay.source_resolver import _load_json


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
            "unmatched": 0,
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
    unmatched_mask = bet_status.eq("unmatched") | settlement_status.eq("unmatched")

    settled_stake = float(stake[settled_mask].sum())
    model_units = float(result_units[settled_mask].sum())
    roi = (model_units / settled_stake * 100.0) if settled_stake else 0.0

    return {
        "total": int(len(df)),
        "settled": int(settled_mask.sum()),
        "open": int((~settled_mask & ~unmatched_mask).sum()),
        "unmatched": int(unmatched_mask.sum()),
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

