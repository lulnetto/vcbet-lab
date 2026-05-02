from __future__ import annotations

from typing import Any


MARKET_PRIORITY = {
    "total_goals": 1,
    "asian_total": 2,
    "asian_handicap": 3,
    "btts": 4,
    "team_total": 5,
}


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "nan", "none", "<na>"}


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
        if _is_missing_value(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_target(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        str(a.get("target_team_role") or "geral") == str(b.get("target_team_role") or "geral")
        and str(a.get("target_team_name") or "geral") == str(b.get("target_team_name") or "geral")
    )


from vcbet.core.selection.asian_ladder import _apply_asian_total_line_ladder
from vcbet.core.selection.correlation import (
    classify_correlation,
    classify_correlation_detail,
    correlation_cluster_key,
    portfolio_selection_score,
)
from vcbet.core.selection.dedupe import _is_contradictory_line, _is_duplicate_or_near_duplicate
from vcbet.core.selection.exposure import _exposure_rejection, _record_exposure
from vcbet.core.selection.line_selection import select_top_picks


__all__ = [
    "MARKET_PRIORITY",
    "_append_flag",
    "_candidate_family_key",
    "market_family",
    "_candidate_to_rejection",
    "_line_float",
    "_same_target",
    "_is_duplicate_or_near_duplicate",
    "_is_contradictory_line",
    "_exposure_rejection",
    "_record_exposure",
    "_apply_asian_total_line_ladder",
    "classify_correlation",
    "classify_correlation_detail",
    "correlation_cluster_key",
    "portfolio_selection_score",
    "select_top_picks",
]
