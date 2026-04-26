from __future__ import annotations

import argparse
from pathlib import Path

from vcbet.core.strategy_config import ConfigResolutionError
from vcbet.paths import REPLAYS_DIR
from vcbet.replay.execution import (
    _compact_picks_for_summary,
    _load_csv_semicolon,
    _load_ledger_csv,
    _load_picks_csv,
    _run_replay_settlement,
    _run_single_replay,
    _summarize_replay_ledger,
)
from vcbet.replay.scoring import (
    CONFIG_ROLE_NOTES,
    CONFIG_ROLE_POLICY,
    MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
    MANUAL_DEFAULT_BASELINE_CONFIG,
    RECOMMENDATION_METHOD,
    _asian_total_line_drift,
    _build_comparison_context,
    _build_config_scorecard,
    _compare_pick_sets,
    _config_role,
    _model_result_summary,
    _normalize_family_signature,
    _normalize_signature,
    _sorted_counter_dict,
)
from vcbet.replay.source_resolver import ROOT, _load_json, _resolve_source_run
from vcbet.replay.summary_builder import replay_configs_for_run

DEFAULT_REPLAY_DIR = REPLAYS_DIR


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


__all__ = [
    "CONFIG_ROLE_NOTES",
    "CONFIG_ROLE_POLICY",
    "DEFAULT_REPLAY_DIR",
    "MANUAL_CONSERVATIVE_REFERENCE_CONFIG",
    "MANUAL_DEFAULT_BASELINE_CONFIG",
    "RECOMMENDATION_METHOD",
    "ROOT",
    "_asian_total_line_drift",
    "_build_comparison_context",
    "_build_config_scorecard",
    "_compact_picks_for_summary",
    "_compare_pick_sets",
    "_config_role",
    "_load_csv_semicolon",
    "_load_json",
    "_load_ledger_csv",
    "_load_picks_csv",
    "_model_result_summary",
    "_normalize_family_signature",
    "_normalize_signature",
    "_resolve_source_run",
    "_run_replay_settlement",
    "_run_single_replay",
    "_sorted_counter_dict",
    "_summarize_replay_ledger",
    "main",
    "replay_configs_for_run",
]


if __name__ == "__main__":
    try:
        main()
    except ConfigResolutionError as exc:
        raise SystemExit(f"[ERRO_CONFIG] {exc}")
