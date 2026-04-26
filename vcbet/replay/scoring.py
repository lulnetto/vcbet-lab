from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


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

