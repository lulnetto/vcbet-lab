from __future__ import annotations

from typing import Any

from vcbet.core.selection import _append_flag, _candidate_family_key, _candidate_to_rejection
from vcbet.core.strategy_config import get_runtime_config


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or str(value).strip().lower() in {"", "nan", "none", "<na>"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_sort_value(candidate: dict[str, Any], name: str, default: float = 0.0) -> float:
    value = _float_or_none(candidate.get(name))
    return default if value is None else value


def _apply_asian_total_line_ladder(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runtime = get_runtime_config()
    portfolio_rules = runtime.rules.get("portfolio", {})
    ladder_rules = portfolio_rules.get("asian_total_line_ladder", {})
    work = [dict(candidate) for candidate in candidates]
    for candidate in work:
        candidate.setdefault("portfolio_line_role", "standard")

    if not ladder_rules.get("enabled", False):
        return work, []

    target_gap = float(ladder_rules.get("target_gap", 0.75))
    tolerance = float(ladder_rules.get("tolerance", 0.26))
    min_gap = float(ladder_rules.get("min_gap_for_secondary", 0.5))
    prefer_lowest = str(ladder_rules.get("primary_line_strategy", "lowest_line")) == "lowest_line"
    fallback_highest = bool(ladder_rules.get("fallback_to_highest_if_no_gap_match", True))

    keep_idx: set[int] = set(range(len(work)))
    rejections: list[dict[str, Any]] = []

    asian_indices = [idx for idx, candidate in enumerate(work) if candidate.get("market_type") == "asian_total"]
    if not asian_indices:
        return work, rejections

    family_map: dict[tuple[Any, ...], list[int]] = {}
    for idx in asian_indices:
        family_map.setdefault(_candidate_family_key(work[idx]), []).append(idx)

    for _, indices in family_map.items():
        if len(indices) < 2:
            continue
        family = [(idx, work[idx], _float_or_none(work[idx].get("line"))) for idx in indices]
        family = [(idx, candidate, line) for idx, candidate, line in family if line is not None]
        if len(family) < 2:
            continue
        family = sorted(
            family,
            key=lambda item: (
                item[2],
                -_candidate_sort_value(item[1], "confidence_score"),
                -_candidate_sort_value(item[1], "ev_percent"),
                _candidate_sort_value(item[1], "odd_entrada"),
            ),
        )

        primary_idx, primary, primary_line = family[0] if prefer_lowest else family[-1]
        work[primary_idx]["portfolio_line_role"] = "asian_total_ladder_primary"
        work[primary_idx]["selection_policy_status"] = "selected"
        selected_indices = {primary_idx}

        secondary_idx: int | None = None
        remaining = [item for item in family if item[0] != primary_idx]
        gap_candidates = [
            (idx, candidate, line, line - float(primary_line))
            for idx, candidate, line in remaining
            if line - float(primary_line) >= min_gap
        ]
        if gap_candidates:
            target_candidates = [
                (idx, candidate, line, gap, abs(gap - target_gap))
                for idx, candidate, line, gap in gap_candidates
                if abs(gap - target_gap) <= tolerance
            ]
            if target_candidates:
                target_candidates = sorted(
                    target_candidates,
                    key=lambda item: (
                        item[4],
                        -_candidate_sort_value(item[1], "confidence_score"),
                        -_candidate_sort_value(item[1], "ev_percent"),
                        item[2],
                    ),
                )
                secondary_idx = target_candidates[0][0]
            elif fallback_highest:
                gap_candidates = sorted(
                    gap_candidates,
                    key=lambda item: (
                        -item[3],
                        -_candidate_sort_value(item[1], "confidence_score"),
                        -_candidate_sort_value(item[1], "ev_percent"),
                    ),
                )
                secondary_idx = gap_candidates[0][0]

        if secondary_idx is not None:
            selected_indices.add(secondary_idx)
            secondary = work[secondary_idx]
            secondary["portfolio_line_role"] = "asian_total_ladder_secondary"
            secondary["selection_policy_status"] = "selected"
            secondary["stake_units"] = min(float(secondary["stake_units"]), 0.5)
            secondary["risk_flags"] = _append_flag(str(secondary["risk_flags"]), "CORRELACAO_JOGO")
            secondary["coexistence_status"] = "keep_both_with_secondary_half_unit"
            secondary["correlation_level"] = "medium"
            secondary["correlated_with_bet_id"] = work[primary_idx].get("bet_id")

        for idx, _, _ in family:
            if idx in selected_indices:
                continue
            keep_idx.discard(idx)
            rejections.append(
                _candidate_to_rejection(
                    work[idx],
                    "ASIAN_TOTAL_LINE_SUPERSEDED",
                    related_bet_id=work[primary_idx].get("bet_id"),
                    details=f"line={float(work[idx]['line']):.2f}|primary_line={float(work[primary_idx]['line']):.2f}",
                )
            )

    filtered = [work[idx] for idx in range(len(work)) if idx in keep_idx]
    return filtered, rejections
