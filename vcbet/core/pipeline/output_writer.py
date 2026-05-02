from __future__ import annotations

import pandas as pd

from vcbet.core.ledger_manager import append_new_picks_to_ledger
from vcbet.core.run_utils import update_manifest
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION


EXPORT_COLS = [
    "bet_id", "run_id", "generated_at", "league", "match_datetime", "home_team", "away_team",
    "match_name", "market_type", "market_scope", "market_raw", "event_url", "selection_raw",
    "sofascore_event_id", "source_event_id", "line", "side", "target_team_role", "target_team_name", "odd_entrada", "odd_justa",
    "prob_model", "ev_percent",
    "pricing_variant", "xg_residual_adjustment_enabled", "xg_observational_flags",
    "home_xg_base", "away_xg_base", "home_xga_base", "away_xga_base",
    "home_goals_for_per_match", "away_goals_for_per_match",
    "home_goals_against_per_match", "away_goals_against_per_match",
    "home_attack_residual", "away_attack_residual",
    "home_defense_residual", "away_defense_residual",
    "home_attack_residual_clamped", "away_attack_residual_clamped",
    "home_defense_residual_clamped", "away_defense_residual_clamped",
    "home_games_estimate", "away_games_estimate",
    "home_residual_shrink", "away_residual_shrink",
    "home_adjusted_attack_xg", "away_adjusted_attack_xg",
    "home_adjusted_defense_xga", "away_adjusted_defense_xga",
    "lambda_home_base", "lambda_away_base",
    "lambda_home_adjusted", "lambda_away_adjusted",
    "lambda_home_adjustment_pct", "lambda_away_adjustment_pct",
    "odd_justa_base", "ev_percent_base", "prob_model_base",
    "odd_justa_adjusted", "ev_percent_adjusted", "prob_model_adjusted",
    "pricing_signal_type", "confidence_score",
    "confidence_score_type", "confidence_score_scale", "stake_units", "entry_reason",
    "risk_flags", "pick_safety_status", "candidate_stage", "safety_gate_reason",
    "decision_policy_status", "decision_reject_reason", "selection_policy_status",
    "selection_reject_reason",
    "entry_quality_score", "entry_quality_tier", "entry_quality_reasons",
    "entry_quality_market_component", "entry_quality_line_protection_component",
    "entry_quality_odds_component", "entry_quality_data_component",
    "entry_quality_risk_component", "entry_quality_ev_component",
    "portfolio_selection_score", "correlation_cluster_key", "correlation_strength",
    "correlation_reason", "portfolio_rank_within_cluster", "selected_over_candidate_id",
    "relation_override_key", "relation_ev_gap_required_pp", "relation_ev_gap_actual_pp",
    "relation_preferred_by", "relation_preferred_reason",
    "portfolio_risk_status", "portfolio_risk_reason", "portfolio_exposure_scope",
    "portfolio_exposure_after", "portfolio_exposure_warning", "market_family",
    "strategy_config_name", "strategy_config_fingerprint", "config_name", "config_fingerprint",
    "config_source_path", "config_snapshot_file", "source_run_id", "source_snapshot_ref",
    "odds_source_run_id", "xg_source_run_id", "odds_snapshot_file", "xg_snapshot_file",
    "odds_snapshot_hash", "xg_snapshot_hash", "odds_snapshot_time", "xg_asof",
    "temporal_contract_version", "temporal_contract_status", "decision_timestamp", "signal_version",
    "pipeline_version", "correlation_level", "coexistence_status",
]


def candidate_artifact_paths(run_dir) -> dict[str, object]:
    return {
        "pick_filter_approved_file": run_dir / "pick_filter_approved.csv",
        "raw_candidates_file": run_dir / "raw_candidates.csv",
        "blocked_candidates_file": run_dir / "blocked_candidates.csv",
        "portfolio_rejected_file": run_dir / "portfolio_rejected.csv",
    }


def write_candidate_artifacts(
    *,
    df_raw_candidates: pd.DataFrame,
    df_candidates: pd.DataFrame,
    df_blocked_candidates: pd.DataFrame,
    df_portfolio_rejected: pd.DataFrame,
    artifact_paths: dict[str, object],
) -> None:
    if not df_raw_candidates.empty:
        df_raw_candidates.to_csv(artifact_paths["raw_candidates_file"], index=False, sep=";", encoding="utf-8-sig")
    if not df_candidates.empty:
        df_candidates.to_csv(artifact_paths["pick_filter_approved_file"], index=False, sep=";", encoding="utf-8-sig")
    if not df_blocked_candidates.empty:
        df_blocked_candidates.to_csv(artifact_paths["blocked_candidates_file"], index=False, sep=";", encoding="utf-8-sig")
    if not df_portfolio_rejected.empty:
        df_portfolio_rejected.to_csv(artifact_paths["portfolio_rejected_file"], index=False, sep=";", encoding="utf-8-sig")


def manifest_common_fields(
    *,
    run_dir,
    pending_rows: list,
    status_counts: dict[str, int],
    quality_report_file,
    run_safety_status: str,
    safety_gate_blocked_total: int,
    runtime_config,
    config_snapshot_file,
    run_id: str,
    odds_path,
    xg_path,
    odds_snapshot_hash: str,
    xg_snapshot_hash: str,
    odds_snapshot_time: str | None,
    xg_asof: str | None,
    temporal_status: str,
    snapshot_validation: dict[str, object],
    signal_version: str,
    pipeline_version: str,
) -> dict[str, object]:
    return {
        "alias_pending_file": str(run_dir / "alias_review_pending.csv"),
        "alias_pending_rows": len(pending_rows),
        "team_match_status_counts": status_counts,
        "quality_report_file": str(quality_report_file),
        "run_safety_status": run_safety_status,
        "safety_gate_blocked_total": safety_gate_blocked_total,
        "strategy_config_name": runtime_config.name,
        "strategy_config_fingerprint": runtime_config.fingerprint,
        "strategy_config_file": str(config_snapshot_file),
        "config_name": runtime_config.name,
        "config_fingerprint": runtime_config.fingerprint,
        "config_source_path": runtime_config.source_path,
        "config_snapshot_file": str(config_snapshot_file),
        "source_run_id": run_id,
        "source_snapshot_ref": f"odds:{odds_path}|xg:{xg_path}",
        "odds_snapshot_hash": odds_snapshot_hash,
        "xg_snapshot_hash": xg_snapshot_hash,
        "odds_snapshot_time": odds_snapshot_time,
        "xg_asof": xg_asof,
        "temporal_contract_version": TEMPORAL_CONTRACT_VERSION,
        "temporal_contract_status": temporal_status,
        "max_snapshot_age_hours": snapshot_validation.get("max_snapshot_age_hours"),
        "snapshot_validation_status": snapshot_validation.get("status"),
        "signal_version": signal_version,
        "pipeline_version": pipeline_version,
    }


def write_pipeline_outputs(
    *,
    df_final: pd.DataFrame,
    modo_debug: bool,
    picks_file,
    ledger_file: str,
    quality_report_file,
    run_dir,
    pending_rows: list,
    status_counts: dict[str, int],
    run_safety_status: str,
    safety_gate_blocked_total: int,
    runtime_config,
    config_snapshot_file,
    run_id: str,
    odds_path,
    xg_path,
    odds_snapshot_hash: str,
    xg_snapshot_hash: str,
    odds_snapshot_time: str | None,
    xg_asof: str | None,
    temporal_status: str,
    snapshot_validation: dict[str, object],
    signal_version: str,
    pipeline_version: str,
) -> None:
    common = manifest_common_fields(
        run_dir=run_dir,
        pending_rows=pending_rows,
        status_counts=status_counts,
        quality_report_file=quality_report_file,
        run_safety_status=run_safety_status,
        safety_gate_blocked_total=safety_gate_blocked_total,
        runtime_config=runtime_config,
        config_snapshot_file=config_snapshot_file,
        run_id=run_id,
        odds_path=odds_path,
        xg_path=xg_path,
        odds_snapshot_hash=odds_snapshot_hash,
        xg_snapshot_hash=xg_snapshot_hash,
        odds_snapshot_time=odds_snapshot_time,
        xg_asof=xg_asof,
        temporal_status=temporal_status,
        snapshot_validation=snapshot_validation,
        signal_version=signal_version,
        pipeline_version=pipeline_version,
    )
    if not df_final.empty:
        export_df = df_final.copy()
        for column in EXPORT_COLS:
            if column not in export_df.columns:
                export_df[column] = pd.NA
        if not modo_debug:
            export_df[EXPORT_COLS].to_csv(picks_file, index=False, sep=";", encoding="utf-8-sig")
            ledger_path, ledger_added_rows, ledger_total_rows = append_new_picks_to_ledger(export_df[EXPORT_COLS], ledger_file)
            print(f"\n[+] Picks exportadas com sucesso: {picks_file}")
            print(f"[+] Ledger atualizado: {ledger_path} | novas={ledger_added_rows} | total={ledger_total_rows}")
            print(f"[+] Quality report salvo: {quality_report_file}")
            update_manifest(
                run_dir,
                status="pipeline_completed",
                picks_file=str(picks_file),
                picks_rows=len(df_final),
                ledger_file=str(ledger_path),
                ledger_added_rows=ledger_added_rows,
                ledger_total_rows=ledger_total_rows,
                **common,
            )
        else:
            print("\n[!] MODO DEBUG: execução concluída sem salvar picks.")
            print(f"[+] Quality report salvo: {quality_report_file}")
            update_manifest(
                run_dir,
                status="pipeline_debug",
                picks_rows=len(df_final),
                **common,
            )
    else:
        print(f"[+] Quality report salvo: {quality_report_file}")
        update_manifest(
            run_dir,
            status="pipeline_empty",
            picks_rows=0,
            **common,
        )
