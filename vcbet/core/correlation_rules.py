from __future__ import annotations

from typing import Any

import pandas as pd

from vcbet.core.strategy_config import get_runtime_config


MARKET_PRIORITY = {
    "total_goals": 1,
    "asian_total": 2,
    "asian_handicap": 3,
    "btts": 4,
    "team_total": 5,
}


def _append_flag(flags: str, new_flag: str) -> str:
    if not flags or flags == "SEM_FLAG":
        return new_flag
    parts = set(flags.split("|"))
    parts.add(new_flag)
    return "|".join(sorted(parts))


def _candidate_family_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        candidate.get("market_type"),
        candidate.get("side"),
        candidate.get("target_team_role"),
        candidate.get("target_team_name"),
    )


def _candidate_to_rejection(candidate: dict[str, Any], reason: str, related_bet_id: str | None = None, details: str | None = None) -> dict[str, Any]:
    payload = dict(candidate)
    payload["portfolio_reject_reason"] = reason
    payload["portfolio_related_bet_id"] = related_bet_id
    payload["portfolio_reject_details"] = details or ""
    return payload


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


def classify_correlation(a: dict[str, Any], b: dict[str, Any]) -> str:
    mt_a, mt_b = a["market_type"], b["market_type"]
    side_a, side_b = a.get("side"), b.get("side")
    line_a = a.get("line")
    line_b = b.get("line")

    if mt_a == "asian_handicap" and mt_b == "asian_handicap":
        same_target = a.get("target_team_role") == b.get("target_team_role") and a.get("target_team_name") == b.get("target_team_name")
        # Linhas AH para o mesmo time/direção são apostas aninhadas, não diversificação.
        # Ex.: +0.5 e -0.25 no mesmo time carregam a mesma tese com draw-risk diferente.
        if same_target and side_a == side_b:
            return "high"
        if side_a != side_b:
            return "high"

    if mt_a == mt_b:
        same_target = a.get("target_team_role") == b.get("target_team_role") and a.get("target_team_name") == b.get("target_team_name")
        if line_a is not None and line_b is not None:
            try:
                fa = float(line_a)
                fb = float(line_b)
            except (TypeError, ValueError):
                fa = fb = None
            if fa is not None and fb is not None:
                if same_target and side_a != side_b and abs(fa - fb) < 1e-9:
                    return "high"

        if side_a == side_b and same_target:
            if line_a is None or line_b is None:
                return "high"
            if abs(float(line_a) - float(line_b)) <= 0.5:
                return "high"
        return "medium"

    pair = {mt_a, mt_b}

    if pair == {"total_goals", "asian_total"}:
        if side_a == side_b and line_a is not None and line_b is not None and abs(float(line_a) - float(line_b)) <= 0.5:
            return "high"
        return "medium"

    if pair == {"total_goals", "btts"}:
        total = a if a["market_type"] == "total_goals" else b
        btts = a if a["market_type"] == "btts" else b
        if total["side"] == "under" and btts["side"] == "no":
            return "high"
        return "medium"

    if pair == {"btts", "team_total"}:
        team = a if a["market_type"] == "team_total" else b
        btts = a if a["market_type"] == "btts" else b
        if btts["side"] == "no" and team["side"] == "under" and float(team.get("line") or 0) <= 0.5:
            return "high"
        return "medium"

    if pair == {"total_goals", "team_total"}:
        total = a if a["market_type"] == "total_goals" else b
        team = a if a["market_type"] == "team_total" else b
        if team["side"] == "over" and total["side"] == "under" and float(total.get("line") or 0) >= 4.0 and float(team.get("line") or 0) <= 0.5:
            return "low"
        return "medium"

    if pair == {"team_total", "asian_handicap"}:
        team = a if a["market_type"] == "team_total" else b
        ah = a if a["market_type"] == "asian_handicap" else b
        if team.get("target_team_role") == ah.get("side"):
            return "medium"
        return "low"

    if pair == {"total_goals", "asian_handicap"}:
        return "medium"

    if pair == {"asian_total", "asian_handicap"}:
        return "medium"

    if pair == {"btts", "asian_handicap"}:
        return "medium"

    return "low"


def select_top_picks(df_candidates: pd.DataFrame, return_meta: bool = False):
    if df_candidates.empty:
        empty = df_candidates.copy()
        empty_rejections = pd.DataFrame()
        return (empty, empty_rejections) if return_meta else empty

    runtime = get_runtime_config()
    portfolio_rules = runtime.rules.get("portfolio", {})
    max_picks_per_match = int(portfolio_rules.get("max_picks_per_match", 2))

    df = df_candidates.copy()
    if "portfolio_line_role" not in df.columns:
        df["portfolio_line_role"] = "standard"
    rejections: list[dict[str, Any]] = []

    kept_rows: list[dict[str, Any]] = []
    for _, raw_group in df.groupby("match_name", sort=False):
        group, ladder_rejections = _apply_asian_total_line_ladder(raw_group)
        rejections.extend(ladder_rejections)
        group = group.sort_values(
            by=["confidence_score", "ev_percent", "market_priority", "odd_entrada", "line"],
            ascending=[False, False, True, True, True],
        )

        selected: list[dict[str, Any]] = []
        for _, row in group.iterrows():
            candidate = row.to_dict()
            if not selected:
                candidate.setdefault("coexistence_status", "keep_primary_only")
                candidate.setdefault("correlation_level", "primary")
                selected.append(candidate)
                continue

            if len(selected) >= max_picks_per_match:
                rejections.append(_candidate_to_rejection(candidate, "MATCH_PICK_CAP_REACHED", related_bet_id=selected[0].get("bet_id")))
                continue

            highest_level = "low"
            primary_ref = None
            skip = False
            for existing in selected:
                level = classify_correlation(existing, candidate)
                if level == "high":
                    rejections.append(_candidate_to_rejection(candidate, "HIGH_CORRELATION_WITH_SELECTED", related_bet_id=existing.get("bet_id")))
                    skip = True
                    break
                if level == "medium":
                    highest_level = "medium"
                    primary_ref = existing.get("bet_id")
            if skip:
                continue

            if highest_level == "medium":
                if not (candidate.get("confidence_score", 0) >= 4 or any(item.get("confidence_score", 0) >= 4 for item in selected)):
                    rejections.append(_candidate_to_rejection(candidate, "MEDIUM_CORRELATION_NO_CONFIDENCE", related_bet_id=primary_ref))
                    continue
                candidate["stake_units"] = min(float(candidate["stake_units"]), 0.5)
                candidate["risk_flags"] = _append_flag(candidate.get("risk_flags", "SEM_FLAG"), "CORRELACAO_JOGO")
                candidate["correlation_level"] = "medium"
                candidate["coexistence_status"] = "keep_both_with_secondary_half_unit"
                candidate["correlated_with_bet_id"] = primary_ref
            else:
                candidate["correlation_level"] = "low"
                candidate["coexistence_status"] = "keep_both"
            selected.append(candidate)

        kept_rows.extend(selected)

    if not kept_rows:
        empty = pd.DataFrame(columns=df_candidates.columns)
        rejection_df = pd.DataFrame(rejections)
        return (empty, rejection_df) if return_meta else empty

    result = pd.DataFrame(kept_rows)
    if "market_priority" in result.columns:
        result = result.drop(columns=["market_priority"])
    result = result.sort_values(by=["confidence_score", "ev_percent", "market_type"], ascending=[False, False, True])
    rejection_df = pd.DataFrame(rejections)
    return (result, rejection_df) if return_meta else result
