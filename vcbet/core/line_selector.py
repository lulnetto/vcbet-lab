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


def market_family(candidate: dict[str, Any]) -> str:
    market_type = str(candidate.get("market_type") or "")
    if market_type in {"total_goals", "asian_total"}:
        return "goals_total"
    if market_type == "team_total":
        return "team_goals"
    if market_type == "asian_handicap":
        return "handicap"
    if market_type == "btts":
        return "btts"
    return market_type or "unknown"


def _candidate_to_rejection(
    candidate: dict[str, Any],
    reason: str,
    related_bet_id: str | None = None,
    details: str | None = None,
    *,
    scope: str | None = None,
    exposure_after: float | None = None,
) -> dict[str, Any]:
    payload = dict(candidate)
    payload["portfolio_reject_reason"] = reason
    payload["portfolio_related_bet_id"] = related_bet_id
    payload["portfolio_reject_details"] = details or ""
    payload["selection_policy_status"] = "rejected_by_line_selector"
    payload["selection_reject_reason"] = reason
    payload["portfolio_risk_status"] = "rejected"
    payload["portfolio_risk_reason"] = reason
    payload["portfolio_exposure_scope"] = scope or ""
    payload["portfolio_exposure_after"] = exposure_after if exposure_after is not None else ""
    payload["market_family"] = payload.get("market_family") or market_family(payload)
    payload["candidate_stage"] = "selection_rejected_candidate"
    return payload


def _line_float(candidate: dict[str, Any]) -> float | None:
    try:
        value = candidate.get("line")
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_target(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        str(a.get("target_team_role") or "geral") == str(b.get("target_team_role") or "geral")
        and str(a.get("target_team_name") or "geral") == str(b.get("target_team_name") or "geral")
    )


def _is_duplicate_or_near_duplicate(a: dict[str, Any], b: dict[str, Any], tolerance: float) -> bool:
    if str(a.get("match_name") or "") != str(b.get("match_name") or ""):
        return False
    if market_family(a) != market_family(b):
        return False
    if str(a.get("side") or "") != str(b.get("side") or ""):
        return False
    if not _same_target(a, b):
        return False
    line_a = _line_float(a)
    line_b = _line_float(b)
    if line_a is None or line_b is None:
        return str(a.get("selection_raw") or "").strip().casefold() == str(b.get("selection_raw") or "").strip().casefold()
    return abs(line_a - line_b) <= tolerance


def _is_contradictory_line(a: dict[str, Any], b: dict[str, Any], tolerance: float) -> bool:
    if str(a.get("match_name") or "") != str(b.get("match_name") or ""):
        return False
    family_a = market_family(a)
    if family_a != market_family(b):
        return False
    side_a = str(a.get("side") or "")
    side_b = str(b.get("side") or "")
    line_a = _line_float(a)
    line_b = _line_float(b)

    if family_a in {"goals_total", "team_goals"}:
        if side_a == side_b or not {side_a, side_b}.issubset({"over", "under"}):
            return False
        if family_a == "team_goals" and not _same_target(a, b):
            return False
        return line_a is not None and line_b is not None and abs(line_a - line_b) <= tolerance

    if family_a == "btts":
        return {side_a, side_b} == {"yes", "no"}

    if family_a == "handicap":
        return side_a != side_b

    return False


def _exposure_rejection(
    candidate: dict[str, Any],
    selected_count_by_scope: dict[tuple[str, str], int],
    selected_stake_by_scope: dict[tuple[str, str], float],
    portfolio_rules: dict[str, Any],
) -> tuple[str, str, float] | None:
    stake = float(candidate.get("stake_units") or 0.0)
    league = str(candidate.get("league") or "unknown")
    family = str(candidate.get("market_family") or market_family(candidate))

    checks = [
        ("league", league, int(portfolio_rules.get("max_picks_per_league", 999)), float(portfolio_rules.get("max_stake_per_league", 999.0))),
        ("market_family", family, int(portfolio_rules.get("max_picks_per_market_family", 999)), float(portfolio_rules.get("max_stake_per_market_family", 999.0))),
    ]
    for scope_name, scope_value, max_count, max_stake in checks:
        key = (scope_name, scope_value)
        next_count = selected_count_by_scope.get(key, 0) + 1
        next_stake = selected_stake_by_scope.get(key, 0.0) + stake
        if next_count > max_count:
            return f"{scope_name.upper()}_PICK_LIMIT", f"{scope_name}:{scope_value}", float(next_count)
        if next_stake > max_stake:
            return f"{scope_name.upper()}_STAKE_LIMIT", f"{scope_name}:{scope_value}", next_stake
    return None


def _record_exposure(
    candidate: dict[str, Any],
    selected_count_by_scope: dict[tuple[str, str], int],
    selected_stake_by_scope: dict[tuple[str, str], float],
) -> None:
    stake = float(candidate.get("stake_units") or 0.0)
    scopes = [
        ("league", str(candidate.get("league") or "unknown")),
        ("market_family", str(candidate.get("market_family") or market_family(candidate))),
    ]
    exposure_parts = []
    exposure_values = []
    for scope_name, scope_value in scopes:
        key = (scope_name, scope_value)
        selected_count_by_scope[key] = selected_count_by_scope.get(key, 0) + 1
        selected_stake_by_scope[key] = selected_stake_by_scope.get(key, 0.0) + stake
        exposure_values.append(selected_stake_by_scope[key])
        exposure_parts.append(f"{scope_name}:{scope_value}={selected_stake_by_scope[key]:.2f}u")
    candidate["portfolio_exposure_scope"] = "|".join(exposure_parts)
    candidate["portfolio_exposure_after"] = round(max(exposure_values) if exposure_values else stake, 4)


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


def classify_correlation(a: dict[str, Any], b: dict[str, Any]) -> str:
    mt_a, mt_b = a["market_type"], b["market_type"]
    side_a, side_b = a.get("side"), b.get("side")
    line_a = a.get("line")
    line_b = b.get("line")

    if mt_a == "asian_handicap" and mt_b == "asian_handicap":
        same_target = a.get("target_team_role") == b.get("target_team_role") and a.get("target_team_name") == b.get("target_team_name")
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
    if "selection_policy_status" not in df.columns:
        df["selection_policy_status"] = "selection_pending"
    df["market_family"] = df.apply(lambda row: market_family(row.to_dict()), axis=1)
    rejections: list[dict[str, Any]] = []
    selected_all: list[dict[str, Any]] = []
    selected_count_by_scope: dict[tuple[str, str], int] = {}
    selected_stake_by_scope: dict[tuple[str, str], float] = {}
    near_duplicate_tolerance = float(portfolio_rules.get("near_duplicate_line_tolerance", 0.25))
    contradictory_tolerance = float(portfolio_rules.get("contradictory_line_tolerance", 0.25))
    medium_correlation_policy = str(portfolio_rules.get("medium_correlation_policy", "downgrade"))

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
            candidate["market_family"] = candidate.get("market_family") or market_family(candidate)

            duplicate_ref = next(
                (
                    existing
                    for existing in selected_all
                    if _is_duplicate_or_near_duplicate(candidate, existing, near_duplicate_tolerance)
                ),
                None,
            )
            if duplicate_ref:
                rejections.append(
                    _candidate_to_rejection(
                        candidate,
                        "DUPLICATE_OR_NEAR_DUPLICATE",
                        related_bet_id=duplicate_ref.get("bet_id"),
                        details=f"family={candidate['market_family']}|line={candidate.get('line')}|ref_line={duplicate_ref.get('line')}",
                        scope="match",
                    )
                )
                continue

            contradiction_ref = next(
                (
                    existing
                    for existing in selected_all
                    if _is_contradictory_line(candidate, existing, contradictory_tolerance)
                ),
                None,
            )
            if contradiction_ref:
                rejections.append(
                    _candidate_to_rejection(
                        candidate,
                        "CONTRADICTORY_LINE_WITH_SELECTED",
                        related_bet_id=contradiction_ref.get("bet_id"),
                        details=f"family={candidate['market_family']}|side={candidate.get('side')}|line={candidate.get('line')}|ref_side={contradiction_ref.get('side')}|ref_line={contradiction_ref.get('line')}",
                        scope="match",
                    )
                )
                continue

            if len(selected) >= max_picks_per_match:
                rejections.append(_candidate_to_rejection(candidate, "MATCH_PICK_CAP_REACHED", related_bet_id=selected[0].get("bet_id"), scope="match"))
                continue

            highest_level = "low"
            primary_ref = None
            skip = False
            for existing in selected:
                level = classify_correlation(existing, candidate)
                if level == "high":
                    rejections.append(_candidate_to_rejection(candidate, "HIGH_CORRELATION_WITH_SELECTED", related_bet_id=existing.get("bet_id"), scope="match"))
                    skip = True
                    break
                if level == "medium":
                    highest_level = "medium"
                    primary_ref = existing.get("bet_id")
            if skip:
                continue

            if highest_level == "medium":
                if medium_correlation_policy == "reject":
                    rejections.append(_candidate_to_rejection(candidate, "MEDIUM_CORRELATION_REJECTED", related_bet_id=primary_ref, scope="match"))
                    continue
                if not (candidate.get("confidence_score", 0) >= 4 or any(item.get("confidence_score", 0) >= 4 for item in selected)):
                    rejections.append(_candidate_to_rejection(candidate, "MEDIUM_CORRELATION_NO_CONFIDENCE", related_bet_id=primary_ref, scope="match"))
                    continue
                candidate["stake_units"] = min(float(candidate["stake_units"]), 0.5)
                candidate["risk_flags"] = _append_flag(candidate.get("risk_flags", "SEM_FLAG"), "CORRELACAO_JOGO")
                candidate["correlation_level"] = "medium"
                candidate["coexistence_status"] = "keep_both_with_secondary_half_unit"
                candidate["correlated_with_bet_id"] = primary_ref
                candidate["portfolio_risk_status"] = "downgraded"
                candidate["portfolio_risk_reason"] = "MEDIUM_CORRELATION_DOWNGRADED"
            else:
                if not selected:
                    candidate.setdefault("coexistence_status", "keep_primary_only")
                    candidate.setdefault("correlation_level", "primary")
                else:
                    candidate["correlation_level"] = "low"
                    candidate["coexistence_status"] = "keep_both"
                candidate.setdefault("portfolio_risk_status", "accepted")
                candidate.setdefault("portfolio_risk_reason", "")

            exposure_rejection = _exposure_rejection(candidate, selected_count_by_scope, selected_stake_by_scope, portfolio_rules)
            if exposure_rejection:
                reason, scope, exposure_after = exposure_rejection
                rejections.append(
                    _candidate_to_rejection(
                        candidate,
                        reason,
                        related_bet_id=selected[0].get("bet_id") if selected else None,
                        details=f"stake_units={float(candidate.get('stake_units') or 0.0):.2f}",
                        scope=scope,
                        exposure_after=exposure_after,
                    )
                )
                continue

            candidate["selection_policy_status"] = "selected"
            _record_exposure(candidate, selected_count_by_scope, selected_stake_by_scope)
            selected.append(candidate)
            selected_all.append(candidate)

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
