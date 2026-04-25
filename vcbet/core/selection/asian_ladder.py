from __future__ import annotations

from typing import Any

import pandas as pd

from vcbet.core.selection import _append_flag, _candidate_family_key, _candidate_to_rejection
from vcbet.core.strategy_config import get_runtime_config


def _apply_asian_total_line_ladder(group: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    runtime = get_runtime_config()
    portfolio_rules = runtime.rules.get("portfolio", {})
    ladder_rules = portfolio_rules.get("asian_total_line_ladder", {})
    if not ladder_rules.get("enabled", False):
        work = group.copy()
        if "portfolio_line_role" not in work.columns:
            work["portfolio_line_role"] = "standard"
        return work, []

    target_gap = float(ladder_rules.get("target_gap", 0.75))
    tolerance = float(ladder_rules.get("tolerance", 0.26))
    min_gap = float(ladder_rules.get("min_gap_for_secondary", 0.5))
    prefer_lowest = str(ladder_rules.get("primary_line_strategy", "lowest_line")) == "lowest_line"
    fallback_highest = bool(ladder_rules.get("fallback_to_highest_if_no_gap_match", True))

    work = group.copy()
    if "portfolio_line_role" not in work.columns:
        work["portfolio_line_role"] = "standard"

    keep_idx: set[int] = set(work.index)
    rejections: list[dict[str, Any]] = []

    asian_mask = work["market_type"] == "asian_total"
    if not asian_mask.any():
        return work, rejections

    asian_df = work.loc[asian_mask].copy()
    family_map: dict[tuple[Any, ...], list[int]] = {}
    for idx, row in asian_df.iterrows():
        family_map.setdefault(_candidate_family_key(row.to_dict()), []).append(idx)

    for _, indices in family_map.items():
        if len(indices) < 2:
            continue
        family = work.loc[indices].copy()
        family = family[pd.to_numeric(family["line"], errors="coerce").notna()].copy()
        if len(family) < 2:
            continue
        family["line_num"] = pd.to_numeric(family["line"], errors="coerce")
        family["ev_num"] = pd.to_numeric(family["ev_percent"], errors="coerce").fillna(0.0)
        family["conf_num"] = pd.to_numeric(family["confidence_score"], errors="coerce").fillna(0.0)
        family = family.sort_values(["line_num", "conf_num", "ev_num", "odd_entrada"], ascending=[True, False, False, True])

        primary = family.iloc[0] if prefer_lowest else family.iloc[-1]
        primary_idx = int(primary.name)
        work.at[primary_idx, "portfolio_line_role"] = "asian_total_ladder_primary"
        work.at[primary_idx, "selection_policy_status"] = "selected"
        selected_indices = {primary_idx}

        remaining = family.loc[family.index != primary_idx].copy()
        secondary_idx: int | None = None
        if not remaining.empty:
            remaining["gap"] = remaining["line_num"] - float(primary["line_num"])
            gap_candidates = remaining.loc[remaining["gap"] >= min_gap].copy()
            if not gap_candidates.empty:
                gap_candidates["gap_distance"] = (gap_candidates["gap"] - target_gap).abs()
                target_candidates = gap_candidates.loc[gap_candidates["gap_distance"] <= tolerance].copy()
                if not target_candidates.empty:
                    target_candidates = target_candidates.sort_values(["gap_distance", "conf_num", "ev_num", "line_num"], ascending=[True, False, False, True])
                    secondary_idx = int(target_candidates.iloc[0].name)
                elif fallback_highest:
                    gap_candidates = gap_candidates.sort_values(["gap", "conf_num", "ev_num"], ascending=[False, False, False])
                    secondary_idx = int(gap_candidates.iloc[0].name)

        if secondary_idx is not None:
            selected_indices.add(secondary_idx)
            work.at[secondary_idx, "portfolio_line_role"] = "asian_total_ladder_secondary"
            work.at[secondary_idx, "selection_policy_status"] = "selected"
            work.at[secondary_idx, "stake_units"] = min(float(work.at[secondary_idx, "stake_units"]), 0.5)
            work.at[secondary_idx, "risk_flags"] = _append_flag(str(work.at[secondary_idx, "risk_flags"]), "CORRELACAO_JOGO")
            work.at[secondary_idx, "coexistence_status"] = "keep_both_with_secondary_half_unit"
            work.at[secondary_idx, "correlation_level"] = "medium"
            work.at[secondary_idx, "correlated_with_bet_id"] = work.at[primary_idx, "bet_id"]

        for idx in family.index:
            if int(idx) in selected_indices:
                continue
            keep_idx.discard(int(idx))
            rejections.append(
                _candidate_to_rejection(
                    work.loc[idx].to_dict(),
                    "ASIAN_TOTAL_LINE_SUPERSEDED",
                    related_bet_id=work.at[primary_idx, "bet_id"],
                    details=f"line={float(work.at[idx, 'line']):.2f}|primary_line={float(work.at[primary_idx, 'line']):.2f}",
                )
            )

    filtered = work.loc[sorted(keep_idx)].copy()
    return filtered, rejections
