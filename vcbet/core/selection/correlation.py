from __future__ import annotations

from typing import Any


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
