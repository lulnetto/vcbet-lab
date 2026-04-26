from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from vcbet.core.selection import MARKET_PRIORITY, _append_flag, _candidate_to_rejection, market_family
from vcbet.core.selection.asian_ladder import _apply_asian_total_line_ladder
from vcbet.core.selection.correlation import classify_correlation
from vcbet.core.selection.dedupe import _is_contradictory_line, _is_duplicate_or_near_duplicate
from vcbet.core.selection.exposure import _exposure_rejection, _record_exposure
from vcbet.core.strategy_config import get_runtime_config


def _numeric_sort_value(candidate: dict[str, Any], field: str, default: float = 0.0) -> float:
    try:
        value = candidate.get(field)
        if value is None or str(value).strip().lower() in {"", "nan", "none", "<na>"}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ascending_line_value(candidate: dict[str, Any]) -> float:
    return _numeric_sort_value(candidate, "line", default=float("inf"))


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_numeric_sort_value(candidate, "confidence_score"),
        -_numeric_sort_value(candidate, "ev_percent"),
        _numeric_sort_value(candidate, "market_priority", default=float(MARKET_PRIORITY.get(str(candidate.get("market_type") or ""), 999))),
        _numeric_sort_value(candidate, "odd_entrada"),
        _ascending_line_value(candidate),
    )


def _result_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_numeric_sort_value(candidate, "confidence_score"),
        -_numeric_sort_value(candidate, "ev_percent"),
        str(candidate.get("market_type") or ""),
    )


def _group_by_match(candidates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for candidate in candidates:
        key = str(candidate.get("match_name") or "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(candidate)
    return [groups[key] for key in order]


def select_top_picks(candidates: Iterable[Mapping[str, Any]], return_meta: bool = False):
    candidate_rows = [dict(candidate) for candidate in candidates]
    if not candidate_rows:
        return ([], []) if return_meta else []

    runtime = get_runtime_config()
    portfolio_rules = runtime.rules.get("portfolio", {})
    max_picks_per_match = int(portfolio_rules.get("max_picks_per_match", 2))

    for candidate in candidate_rows:
        candidate.setdefault("portfolio_line_role", "standard")
        candidate.setdefault("selection_policy_status", "selection_pending")
        candidate["market_family"] = candidate.get("market_family") or market_family(candidate)

    rejections: list[dict[str, Any]] = []
    selected_all: list[dict[str, Any]] = []
    selected_count_by_scope: dict[tuple[str, str], int] = {}
    selected_stake_by_scope: dict[tuple[str, str], float] = {}
    near_duplicate_tolerance = float(portfolio_rules.get("near_duplicate_line_tolerance", 0.25))
    contradictory_tolerance = float(portfolio_rules.get("contradictory_line_tolerance", 0.25))
    medium_correlation_policy = str(portfolio_rules.get("medium_correlation_policy", "downgrade"))

    kept_rows: list[dict[str, Any]] = []
    for raw_group in _group_by_match(candidate_rows):
        group, ladder_rejections = _apply_asian_total_line_ladder(raw_group)
        rejections.extend(ladder_rejections)
        group = sorted(group, key=_candidate_sort_key)

        selected: list[dict[str, Any]] = []
        for row in group:
            candidate = dict(row)
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
        return ([], rejections) if return_meta else []

    result = []
    for candidate in kept_rows:
        payload = dict(candidate)
        payload.pop("market_priority", None)
        result.append(payload)
    result = sorted(result, key=_result_sort_key)
    return (result, rejections) if return_meta else result
