from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from vcbet.core.data_health import validate_snapshot_health
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE
from vcbet.core.pipeline.filtering_stage import build_normalization_filter, select_and_annotate_final_picks
from vcbet.core.pipeline.input_loader import carregar_snapshot_odds, carregar_snapshot_xg, load_pipeline_inputs
from vcbet.core.pipeline.output_writer import candidate_artifact_paths, write_candidate_artifacts, write_pipeline_outputs
from vcbet.core.pipeline.pricing_stage import build_priced_candidates
from vcbet.core.pipeline.quality_report import (
    build_snapshot_rejection_report,
    build_quality_report,
    print_pricing_summary,
    print_scan_report,
    save_run_quality_report,
    to_sorted_dict,
)
from vcbet.core.pipeline.team_resolution import prepare_team_resolution_state
from vcbet.core.run_utils import load_json_file, now_str, update_manifest
from vcbet.core.strategy_config import configure_runtime
from vcbet.core.temporal_contract import SnapshotValidator, temporal_contract_status


HIGH_MATCH_THRESHOLD = 90
REVIEW_MATCH_THRESHOLD = 75
SUPPORTED_MARKETS = {
    "total_goals",
    "team_total",
    "btts",
    "asian_total",
    "asian_handicap",
}
SIGNAL_VERSION = "ev_pipeline_v1"
PIPELINE_VERSION = "pipeline_ev_phase3_provenance"


def processar_pipeline(
    odds_file: str,
    xg_file: str,
    run_id: str | None = None,
    output_dir: str = "data/runs",
    alias_file: str = "alias_times.json",
    ledger_file: str = str(DEFAULT_LEDGER_FILE),
    modo_debug: bool = False,
    config_file: str | None = None,
    config_name: str | None = None,
    snapshot_reference_timestamp: str | None = None,
):
    runtime_config = configure_runtime(config_name=config_name, config_file=config_file)
    loaded = load_pipeline_inputs(
        odds_file=odds_file,
        xg_file=xg_file,
        run_id=run_id,
        output_dir=output_dir,
        runtime_config=runtime_config,
    )
    df_betano = loaded["df_betano"]
    df_xg = loaded["df_xg"]

    odds_manifest_path = Path(loaded["run_dir"]) / "odds_collection_manifest.json"
    odds_manifest = load_json_file(odds_manifest_path) if odds_manifest_path.exists() else None

    snapshot_health = validate_snapshot_health(
        df_betano,
        df_xg,
        max_invalid_snapshot_row_rate=runtime_config.data_quality.get("max_invalid_snapshot_row_rate", 0.25),
        require_snapshot_health_ok=runtime_config.data_quality.get("require_snapshot_health_ok", True),
        odds_manifest=odds_manifest,
    )
    if not snapshot_health["is_valid"]:
        generated_at = now_str()
        temporal_status = temporal_contract_status(
            decision_timestamp=generated_at,
            odds_snapshot_time=loaded["odds_snapshot_time"],
            xg_asof=loaded["xg_asof"],
        )
        quality_report = build_snapshot_rejection_report(
            run_id=loaded["run_id"],
            target_date=loaded["target_date"],
            runtime_config=runtime_config,
            config_snapshot_file=loaded["config_snapshot_file"],
            generated_at=generated_at,
            odds_path=loaded["odds_path"],
            xg_path=loaded["xg_path"],
            odds_run_id=loaded["odds_run_id"],
            xg_run_id=loaded["xg_run_id"],
            odds_snapshot_hash=loaded["odds_snapshot_hash"],
            xg_snapshot_hash=loaded["xg_snapshot_hash"],
            odds_snapshot_time=loaded["odds_snapshot_time"],
            xg_asof=loaded["xg_asof"],
            temporal_status=temporal_status,
            snapshot_validation={
                "status": "rejected",
                "errors": snapshot_health["errors"],
                "max_snapshot_age_hours": runtime_config.max_snapshot_age_hours,
            },
            signal_version=SIGNAL_VERSION,
            pipeline_version=PIPELINE_VERSION,
            alias_file=alias_file,
            ledger_file=ledger_file,
        )
        quality_report["error"] = {
            "code": "snapshot_health_check_failed",
            "message": "Snapshot health check rejected odds/xG inputs before pricing.",
            "details": snapshot_health["errors"],
        }
        quality_report["data_quality"]["snapshot_health"] = snapshot_health
        quality_report_file = save_run_quality_report(loaded["run_dir"], quality_report)
        update_manifest(
            loaded["run_dir"],
            status="pipeline_rejected_snapshot_health",
            picks_rows=0,
            quality_report_file=str(quality_report_file),
            run_safety_status="rejected_snapshot_health",
            safety_gate_blocked_total=0,
            strategy_config_name=runtime_config.name,
            strategy_config_fingerprint=runtime_config.fingerprint,
            strategy_config_file=str(loaded["config_snapshot_file"]),
            config_name=runtime_config.name,
            config_fingerprint=runtime_config.fingerprint,
            config_source_path=runtime_config.source_path,
            config_snapshot_file=str(loaded["config_snapshot_file"]),
            source_run_id=loaded["run_id"],
            source_snapshot_ref=f"odds:{loaded['odds_path']}|xg:{loaded['xg_path']}",
            odds_snapshot_hash=loaded["odds_snapshot_hash"],
            xg_snapshot_hash=loaded["xg_snapshot_hash"],
            odds_snapshot_time=loaded["odds_snapshot_time"],
            xg_asof=loaded["xg_asof"],
            temporal_contract_status=temporal_status,
            max_snapshot_age_hours=runtime_config.max_snapshot_age_hours,
            snapshot_validation_status="rejected",
            signal_version=SIGNAL_VERSION,
            pipeline_version=PIPELINE_VERSION,
        )
        error_codes = ", ".join(str(item.get("code")) for item in snapshot_health["errors"])
        raise ValueError(f"Snapshot health check failed: {error_codes}")

    generated_at = now_str()
    snapshot_validation_reference = snapshot_reference_timestamp or generated_at
    temporal_status = temporal_contract_status(
        decision_timestamp=generated_at,
        odds_snapshot_time=loaded["odds_snapshot_time"],
        xg_asof=loaded["xg_asof"],
    )
    snapshot_validation_result = SnapshotValidator(
        max_snapshot_age_hours=runtime_config.max_snapshot_age_hours,
    ).validate(
        decision_timestamp=snapshot_validation_reference,
        odds_snapshot_time=loaded["odds_snapshot_time"],
        xg_asof=loaded["xg_asof"],
    )
    snapshot_validation = snapshot_validation_result.to_dict()
    if not snapshot_validation_result.is_valid:
        quality_report = build_snapshot_rejection_report(
            run_id=loaded["run_id"],
            target_date=loaded["target_date"],
            runtime_config=runtime_config,
            config_snapshot_file=loaded["config_snapshot_file"],
            generated_at=generated_at,
            odds_path=loaded["odds_path"],
            xg_path=loaded["xg_path"],
            odds_run_id=loaded["odds_run_id"],
            xg_run_id=loaded["xg_run_id"],
            odds_snapshot_hash=loaded["odds_snapshot_hash"],
            xg_snapshot_hash=loaded["xg_snapshot_hash"],
            odds_snapshot_time=loaded["odds_snapshot_time"],
            xg_asof=loaded["xg_asof"],
            temporal_status=temporal_status,
            snapshot_validation=snapshot_validation,
            signal_version=SIGNAL_VERSION,
            pipeline_version=PIPELINE_VERSION,
            alias_file=alias_file,
            ledger_file=ledger_file,
        )
        quality_report_file = save_run_quality_report(loaded["run_dir"], quality_report)
        update_manifest(
            loaded["run_dir"],
            status="pipeline_rejected_snapshot",
            picks_rows=0,
            quality_report_file=str(quality_report_file),
            run_safety_status="rejected_snapshot",
            safety_gate_blocked_total=0,
            strategy_config_name=runtime_config.name,
            strategy_config_fingerprint=runtime_config.fingerprint,
            strategy_config_file=str(loaded["config_snapshot_file"]),
            config_name=runtime_config.name,
            config_fingerprint=runtime_config.fingerprint,
            config_source_path=runtime_config.source_path,
            config_snapshot_file=str(loaded["config_snapshot_file"]),
            source_run_id=loaded["run_id"],
            source_snapshot_ref=f"odds:{loaded['odds_path']}|xg:{loaded['xg_path']}",
            odds_snapshot_hash=loaded["odds_snapshot_hash"],
            xg_snapshot_hash=loaded["xg_snapshot_hash"],
            odds_snapshot_time=loaded["odds_snapshot_time"],
            xg_asof=loaded["xg_asof"],
            temporal_contract_status=temporal_status,
            max_snapshot_age_hours=snapshot_validation["max_snapshot_age_hours"],
            snapshot_validation_status=snapshot_validation["status"],
            signal_version=SIGNAL_VERSION,
            pipeline_version=PIPELINE_VERSION,
        )
        error_codes = ", ".join(str(item.get("code")) for item in snapshot_validation["errors"])
        raise ValueError(f"SnapshotValidator rejected snapshots: {error_codes}")

    normalization = build_normalization_filter(df_betano, df_xg, SUPPORTED_MARKETS)
    resolution_state = prepare_team_resolution_state(alias_file, df_xg)
    pricing = build_priced_candidates(
        df_alvo=normalization["df_alvo"],
        resolution_state=resolution_state,
        run_id=loaded["run_id"],
        odds_run_id=loaded["odds_run_id"],
        xg_run_id=loaded["xg_run_id"],
        generated_at=generated_at,
        alias_pending_file=loaded["alias_pending_file"],
        high_match_threshold=HIGH_MATCH_THRESHOLD,
        review_match_threshold=REVIEW_MATCH_THRESHOLD,
    )

    df_candidates = pd.DataFrame(pricing["candidate_rows"])
    df_raw_candidates = pd.DataFrame(pricing["raw_candidate_rows"])
    df_blocked_candidates = pd.DataFrame(pricing["blocked_candidate_rows"])
    artifact_paths = candidate_artifact_paths(loaded["run_dir"])
    selection = select_and_annotate_final_picks(
        df_candidates=df_candidates,
        df_blocked_candidates=df_blocked_candidates,
        generated_at=generated_at,
        runtime_config=runtime_config,
        config_snapshot_file=loaded["config_snapshot_file"],
        run_id=loaded["run_id"],
        odds_path=loaded["odds_path"],
        xg_path=loaded["xg_path"],
        odds_snapshot_hash=loaded["odds_snapshot_hash"],
        xg_snapshot_hash=loaded["xg_snapshot_hash"],
        odds_snapshot_time=loaded["odds_snapshot_time"],
        xg_asof=loaded["xg_asof"],
        temporal_status=temporal_status,
        signal_version=SIGNAL_VERSION,
        pipeline_version=PIPELINE_VERSION,
    )
    write_candidate_artifacts(
        df_raw_candidates=df_raw_candidates,
        df_candidates=df_candidates,
        df_blocked_candidates=df_blocked_candidates,
        df_portfolio_rejected=selection["df_portfolio_rejected"],
        artifact_paths=artifact_paths,
    )
    print_pricing_summary(
        priced_market_counts=pricing["priced_market_counts"],
        df_candidates=df_candidates,
        safety_gate_blocked_total=selection["safety_gate_blocked_total"],
        df_final=selection["df_final"],
        processing_discard_counts=pricing["processing_discard_counts"],
        approved_market_counts=pricing["approved_market_counts"],
    )
    final_counters = print_scan_report(selection["df_final"])
    quality_report = build_quality_report(
        run_id=loaded["run_id"],
        target_date=loaded["target_date"],
        runtime_config=runtime_config,
        config_snapshot_file=loaded["config_snapshot_file"],
        generated_at=generated_at,
        odds_path=loaded["odds_path"],
        xg_path=loaded["xg_path"],
        odds_run_id=loaded["odds_run_id"],
        xg_run_id=loaded["xg_run_id"],
        odds_snapshot_hash=loaded["odds_snapshot_hash"],
        xg_snapshot_hash=loaded["xg_snapshot_hash"],
        odds_snapshot_time=loaded["odds_snapshot_time"],
        xg_asof=loaded["xg_asof"],
        temporal_status=temporal_status,
        snapshot_validation=snapshot_validation,
        signal_version=SIGNAL_VERSION,
        pipeline_version=PIPELINE_VERSION,
        alias_file=alias_file,
        ledger_file=ledger_file,
        df_betano=df_betano,
        df_xg=df_xg,
        df_alvo=normalization["df_alvo"],
        normalized_status_counts=normalization["normalized_status_counts"],
        market_scope_counts=normalization["market_scope_counts"],
        normalized_market_type_counts=normalization["normalized_market_type_counts"],
        base_filter_discard_counts=normalization["base_filter_discard_counts"],
        status_counts=pricing["status_counts"],
        pending_rows=pricing["pending_rows"],
        unique_pending_counts=pricing["unique_pending_counts"],
        unique_pending_by_league=pricing["unique_pending_by_league"],
        registry_stale_leagues=pricing["registry_stale_leagues"],
        processing_discard_counts=pricing["processing_discard_counts"],
        df_raw_candidates=df_raw_candidates,
        priced_market_counts=pricing["priced_market_counts"],
        df_candidates=df_candidates,
        approved_market_counts=pricing["approved_market_counts"],
        df_blocked_candidates=df_blocked_candidates,
        safety_gate_blocked_total=selection["safety_gate_blocked_total"],
        df_portfolio_rejected=selection["df_portfolio_rejected"],
        run_safety_status=selection["run_safety_status"],
        official_unsafe_total=selection["official_unsafe_total"],
        df_final=selection["df_final"],
        final_picks_by_market=final_counters["final_picks_by_market"],
        final_picks_by_league=final_counters["final_picks_by_league"],
        final_picks_by_confidence=final_counters["final_picks_by_confidence"],
        alias_pending_file=loaded["alias_pending_file"],
        raw_candidates_file=artifact_paths["raw_candidates_file"],
        blocked_candidates_file=artifact_paths["blocked_candidates_file"],
        pick_filter_approved_file=artifact_paths["pick_filter_approved_file"],
        portfolio_rejected_file=artifact_paths["portfolio_rejected_file"],
        picks_file=loaded["picks_file"],
    )
    quality_report_file = save_run_quality_report(loaded["run_dir"], quality_report)
    write_pipeline_outputs(
        df_final=selection["df_final"],
        modo_debug=modo_debug,
        picks_file=loaded["picks_file"],
        ledger_file=ledger_file,
        quality_report_file=quality_report_file,
        run_dir=loaded["run_dir"],
        pending_rows=pricing["pending_rows"],
        status_counts=pricing["status_counts"],
        run_safety_status=selection["run_safety_status"],
        safety_gate_blocked_total=selection["safety_gate_blocked_total"],
        runtime_config=runtime_config,
        config_snapshot_file=loaded["config_snapshot_file"],
        run_id=loaded["run_id"],
        odds_path=loaded["odds_path"],
        xg_path=loaded["xg_path"],
        odds_snapshot_hash=loaded["odds_snapshot_hash"],
        xg_snapshot_hash=loaded["xg_snapshot_hash"],
        odds_snapshot_time=loaded["odds_snapshot_time"],
        xg_asof=loaded["xg_asof"],
        temporal_status=temporal_status,
        snapshot_validation=snapshot_validation,
        signal_version=SIGNAL_VERSION,
        pipeline_version=PIPELINE_VERSION,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline EV com pricing estruturado")
    parser.add_argument("--odds-file", required=True, help="Caminho do odds_snapshot.csv")
    parser.add_argument("--xg-file", required=True, help="Caminho do xg_snapshot.csv")
    parser.add_argument("--run-id", help="Identificador único da execução")
    parser.add_argument("--output-dir", default="data/runs", help="Diretório base para salvar as runs")
    parser.add_argument("--alias-file", default="alias_times.json", help="Arquivo JSON com aliases aprovados manualmente")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="Caminho do bets_ledger.csv")
    parser.add_argument("--debug", action="store_true", help="Executa normalmente, mas não salva arquivos no final")
    parser.add_argument("--config-file", help="Arquivo JSON de configuração de estratégia")
    parser.add_argument("--config-name", help="Nome do preset em ./configs sem .json")
    parser.add_argument("--snapshot-reference-timestamp", help="Timestamp de referência para validação temporal de snapshots, usado por replay histórico")
    args = parser.parse_args()

    processar_pipeline(
        odds_file=args.odds_file,
        xg_file=args.xg_file,
        run_id=args.run_id,
        output_dir=args.output_dir,
        alias_file=args.alias_file,
        ledger_file=args.ledger_file,
        modo_debug=args.debug,
        config_file=args.config_file,
        config_name=args.config_name,
        snapshot_reference_timestamp=args.snapshot_reference_timestamp,
    )
