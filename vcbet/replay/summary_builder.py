from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from vcbet.core.strategy_config import list_available_configs
from vcbet.replay.execution import _run_single_replay
from vcbet.replay.scoring import (
    MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
    MANUAL_DEFAULT_BASELINE_CONFIG,
    RECOMMENDATION_METHOD,
    _build_comparison_context,
    _build_config_scorecard,
)
from vcbet.replay.source_resolver import _resolve_source_run


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
    summary: dict[str, Any] = {
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

