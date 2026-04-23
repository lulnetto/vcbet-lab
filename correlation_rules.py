from __future__ import annotations

from typing import Any

import pandas as pd


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


def classify_correlation(a: dict[str, Any], b: dict[str, Any]) -> str:
    mt_a, mt_b = a["market_type"], b["market_type"]
    side_a, side_b = a.get("side"), b.get("side")
    line_a = a.get("line")
    line_b = b.get("line")

    # Regra dura da v1: no mesmo jogo, dois Asian Handicaps em lados opostos
    # nunca coexistem, mesmo com linhas diferentes.
    # Ex.: Casa Pia +0.5 e Braga -0.75.
    if mt_a == "asian_handicap" and mt_b == "asian_handicap" and side_a != side_b:
        return "high"

    if mt_a == mt_b:
        same_target = a.get("target_team_role") == b.get("target_team_role") and a.get("target_team_name") == b.get("target_team_name")

        # Conflito absoluto: lados opostos da mesma linha no mesmo mercado/alvo.
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


def select_top_picks(df_candidates: pd.DataFrame) -> pd.DataFrame:
    if df_candidates.empty:
        return df_candidates.copy()

    df = df_candidates.copy()
    df = df.sort_values(
        by=["match_name", "confidence_score", "ev_percent", "market_priority", "odd_entrada"],
        ascending=[True, False, False, True, True],
    )

    kept_rows: list[dict[str, Any]] = []
    for match_name, group in df.groupby("match_name", sort=False):
        selected: list[dict[str, Any]] = []
        for _, row in group.iterrows():
            candidate = row.to_dict()
            if not selected:
                candidate["correlation_level"] = "primary"
                candidate["coexistence_status"] = "keep_primary_only"
                selected.append(candidate)
                continue

            if len(selected) >= 2:
                continue

            highest_level = "low"
            primary_ref = None
            skip = False
            for existing in selected:
                level = classify_correlation(existing, candidate)
                if level == "high":
                    skip = True
                    break
                if level == "medium":
                    highest_level = "medium"
                    primary_ref = existing["bet_id"]
            if skip:
                continue

            if highest_level == "medium":
                if not (candidate["confidence_score"] >= 4 or any(item["confidence_score"] >= 4 for item in selected)):
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
        return pd.DataFrame(columns=df_candidates.columns)

    result = pd.DataFrame(kept_rows)
    if "market_priority" in result.columns:
        result = result.drop(columns=["market_priority"])
    return result.sort_values(by=["confidence_score", "ev_percent", "market_type"], ascending=[False, False, True])
