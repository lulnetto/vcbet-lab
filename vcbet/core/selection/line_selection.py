from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from vcbet.core.selection import MARKET_PRIORITY, _append_flag, _candidate_to_rejection, market_family
from vcbet.core.selection.asian_ladder import _apply_asian_total_line_ladder
from vcbet.core.selection.correlation import (
    HARD_CORRELATION_STRENGTHS,
    TOTAL_PROTECTED_RELATION_KEYS,
    TOTAL_RELATION_KEYS,
    classify_correlation_detail,
    correlation_cluster_key,
    merge_correlation_selection_config,
    odds_quality_bonus,
    portfolio_selection_score,
    relation_override_key,
    risk_penalty,
    selection_safety_bonus,
)
from vcbet.core.selection.entry_quality import annotate_entry_quality
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


def _portfolio_score_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_numeric_sort_value(candidate, "portfolio_selection_score"),
        -_numeric_sort_value(candidate, "ev_percent"),
        -_numeric_sort_value(candidate, "confidence_score"),
        -_numeric_sort_value(candidate, "selection_safety_bonus"),
        _numeric_sort_value(candidate, "odd_entrada"),
        str(candidate.get("market_type") or ""),
        str(candidate.get("selection_raw") or ""),
        str(candidate.get("bet_id") or ""),
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


def _is_enabled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "disabled", "none", "null"}


def _strength_rank(strength: str) -> int:
    return {
        "low": 0,
        "medium": 1,
        "near_duplicate": 2,
        "high": 3,
        "equivalent": 4,
        "contradictory": 5,
    }.get(str(strength or "low"), 0)


def _portfolio_reject_reason(strength: str) -> str:
    if strength == "contradictory":
        return "CONTRADICTORY_WITH_SELECTED"
    if strength in {"equivalent", "near_duplicate"}:
        return "EQUIVALENT_MARKET_LOWER_SCORE"
    return "HIGH_CORRELATION_LOWER_SCORE"


def _component_cluster_key(rows: list[dict[str, Any]], reasons: set[str]) -> str:
    if len(rows) == 1:
        return correlation_cluster_key(rows[0])
    match_name = str(rows[0].get("match_name") or "-")
    target_roles = sorted({str(row.get("target_team_role") or "geral") for row in rows})
    target_names = sorted({str(row.get("target_team_name") or "geral") for row in rows})
    sides = sorted({str(row.get("side") or "-") for row in rows})
    reason_part = "+".join(sorted(reason for reason in reasons if reason)) or "CORRELATED_CLUSTER"
    thesis_part = "||".join(sorted(correlation_cluster_key(row) for row in rows))
    return (
        f"match={match_name}|reason={reason_part}|roles={','.join(target_roles)}|"
        f"targets={','.join(target_names)}|sides={','.join(sides)}|thesis={thesis_part}"
    )


RELATION_AUDIT_FIELDS = (
    "relation_override_key",
    "relation_ev_gap_required_pp",
    "relation_ev_gap_actual_pp",
    "relation_preferred_by",
    "relation_preferred_reason",
)


def _optional_numeric(candidate: dict[str, Any], field: str) -> float | None:
    try:
        value = candidate.get(field)
        if value is None or str(value).strip().lower() in {"", "nan", "none", "<na>"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _total_line_distance_key(distance: float) -> list[str]:
    rounded = round(distance, 2)
    return [
        f"{rounded:.2f}".rstrip("0").rstrip("."),
        f"{rounded:.1f}",
        str(rounded),
    ]


def _total_line_relation_threshold(
    a: dict[str, Any],
    b: dict[str, Any],
    correlation_config: dict[str, Any],
) -> float:
    default = correlation_config.get("total_line_default_ev_gap_override_pp", 5.0)
    line_a = _optional_numeric(a, "line")
    line_b = _optional_numeric(b, "line")
    by_distance = correlation_config.get("total_line_ev_gap_override_by_distance")
    if line_a is not None and line_b is not None and isinstance(by_distance, Mapping):
        distance = abs(line_a - line_b)
        for key in _total_line_distance_key(distance):
            if key in by_distance:
                try:
                    return float(by_distance[key])
                except (TypeError, ValueError):
                    break
    try:
        return float(default)
    except (TypeError, ValueError):
        return 5.0


def _relation_threshold(
    relation_key: str,
    correlation_config: dict[str, Any],
    a: dict[str, Any] | None = None,
    b: dict[str, Any] | None = None,
) -> float:
    if relation_key in TOTAL_PROTECTED_RELATION_KEYS and a is not None and b is not None:
        return _total_line_relation_threshold(a, b, correlation_config)

    configured = None
    by_relation = correlation_config.get("ev_gap_override_by_relation")
    if isinstance(by_relation, Mapping):
        configured = by_relation.get(relation_key)
    if configured is None:
        configured = correlation_config.get("ev_gap_override_pp", 2.0)
    try:
        return float(configured)
    except (TypeError, ValueError):
        return float(correlation_config.get("ev_gap_override_pp", 2.0))


def _relation_protection_rank(candidate: dict[str, Any]) -> float:
    market_type = str(candidate.get("market_type") or "").strip().casefold()
    if market_type == "draw_no_bet":
        return 100.0
    if market_type == "asian_handicap":
        line = _optional_numeric(candidate, "line")
        return 100.0 if line is None else 100.0 + line
    if market_type in {"total_goals", "asian_total"}:
        line = _optional_numeric(candidate, "line")
        side = str(candidate.get("side") or "").strip().casefold()
        if line is None:
            return 50.0
        if side == "over":
            return 100.0 - line
        if side == "under":
            return 100.0 + line
    return selection_safety_bonus(candidate)


def _relation_tournament_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_relation_protection_rank(candidate),
        -_numeric_sort_value(candidate, "ev_percent"),
        *_portfolio_score_sort_key(candidate),
    )


def _regular_winner_for_cluster(rows: list[dict[str, Any]], correlation_config: dict[str, Any]) -> dict[str, Any]:
    score_best = min(rows, key=_portfolio_score_sort_key)
    ev_best = max(
        rows,
        key=lambda row: (
            _numeric_sort_value(row, "ev_percent"),
            _numeric_sort_value(row, "portfolio_selection_score"),
            _numeric_sort_value(row, "confidence_score"),
            str(row.get("bet_id") or ""),
        ),
    )
    ev_gap = _numeric_sort_value(ev_best, "ev_percent") - _numeric_sort_value(score_best, "ev_percent")
    if ev_best is not score_best and ev_gap >= float(correlation_config.get("ev_gap_override_pp", 2.0)):
        return ev_best
    return score_best


def _relation_pair_decision(
    a: dict[str, Any],
    b: dict[str, Any],
    correlation_config: dict[str, Any],
    *,
    near_duplicate_tolerance: float,
) -> dict[str, Any] | None:
    relation_key = relation_override_key(a, b, near_duplicate_tolerance=near_duplicate_tolerance)
    if not relation_key:
        return None

    required_gap = _relation_threshold(relation_key, correlation_config, a, b)
    ev_a = _numeric_sort_value(a, "ev_percent")
    ev_b = _numeric_sort_value(b, "ev_percent")
    protection_a = _relation_protection_rank(a)
    protection_b = _relation_protection_rank(b)

    if relation_key in {"DNB_EQUALS_AH_0", "TOTAL_EQUALS_ASIAN_TOTAL"}:
        if abs(ev_a - ev_b) > 1e-9:
            winner = a if ev_a > ev_b else b
            preferred_by = "equivalent_ev"
            preferred_reason = (
                "equivalent_total_line_higher_ev"
                if relation_key == "TOTAL_EQUALS_ASIAN_TOTAL"
                else "equivalent_market_higher_ev"
            )
        else:
            winner = min([a, b], key=_portfolio_score_sort_key)
            preferred_by = "regular_score"
            preferred_reason = (
                "equivalent_total_line_score_tiebreaker"
                if relation_key == "TOTAL_EQUALS_ASIAN_TOTAL"
                else "equivalent_market_score_tiebreaker"
            )
        loser = b if winner is a else a
        actual_gap = abs(ev_a - ev_b)
        return {
            "winner": winner,
            "loser": loser,
            "relation_key": relation_key,
            "required_gap": required_gap,
            "actual_gap": round(actual_gap, 6),
            "preferred_by": preferred_by,
            "preferred_reason": preferred_reason,
        }

    if abs(protection_a - protection_b) <= 1e-9:
        winner = _regular_winner_for_cluster([a, b], correlation_config)
        loser = b if winner is a else a
        return {
            "winner": winner,
            "loser": loser,
            "relation_key": relation_key,
            "required_gap": required_gap,
            "actual_gap": round(abs(ev_a - ev_b), 6),
            "preferred_by": "regular_score",
            "preferred_reason": "equal_protection_regular_score_tiebreaker",
        }

    protected = a if protection_a > protection_b else b
    less_protected = b if protected is a else a
    actual_gap = _numeric_sort_value(less_protected, "ev_percent") - _numeric_sort_value(protected, "ev_percent")
    if actual_gap >= required_gap:
        winner = less_protected
        loser = protected
        preferred_by = "ev_gap"
        preferred_reason = (
            "less_protected_total_line_wins_ev_gap_threshold_met"
            if relation_key in TOTAL_RELATION_KEYS
            else "less_protected_line_wins_ev_gap_threshold_met"
        )
    else:
        winner = protected
        loser = less_protected
        preferred_by = "protection"
        preferred_reason = (
            "protected_total_line_wins_ev_gap_below_threshold"
            if relation_key in TOTAL_RELATION_KEYS
            else "protected_line_wins_ev_gap_below_threshold"
        )

    return {
        "winner": winner,
        "loser": loser,
        "relation_key": relation_key,
        "required_gap": required_gap,
        "actual_gap": round(actual_gap, 6),
        "preferred_by": preferred_by,
        "preferred_reason": preferred_reason,
    }


def _apply_relation_audit(decision: dict[str, Any]) -> None:
    audit = {
        "relation_override_key": decision["relation_key"],
        "relation_ev_gap_required_pp": decision["required_gap"],
        "relation_ev_gap_actual_pp": decision["actual_gap"],
        "relation_preferred_by": decision["preferred_by"],
        "relation_preferred_reason": decision["preferred_reason"],
    }
    decision["winner"].update(audit)
    decision["loser"].update(audit)


def _relation_audit_details(candidate: dict[str, Any]) -> str:
    if not candidate.get("relation_override_key"):
        return ""
    return (
        f"|relation_override_key={candidate.get('relation_override_key')}"
        f"|relation_ev_gap_required_pp={candidate.get('relation_ev_gap_required_pp')}"
        f"|relation_ev_gap_actual_pp={candidate.get('relation_ev_gap_actual_pp')}"
        f"|relation_preferred_by={candidate.get('relation_preferred_by')}"
        f"|relation_preferred_reason={candidate.get('relation_preferred_reason')}"
    )


def _winner_for_cluster(
    rows: list[dict[str, Any]],
    correlation_config: dict[str, Any],
    *,
    near_duplicate_tolerance: float,
) -> dict[str, Any]:
    if len(rows) <= 1:
        return rows[0]

    has_relation_override = any(
        relation_override_key(rows[left_idx], rows[right_idx], near_duplicate_tolerance=near_duplicate_tolerance)
        for left_idx in range(len(rows))
        for right_idx in range(left_idx + 1, len(rows))
    )
    if not has_relation_override:
        return _regular_winner_for_cluster(rows, correlation_config)

    winner = sorted(rows, key=_relation_tournament_sort_key)[0]
    applied_relation_rule = False
    for challenger in sorted([row for row in rows if row is not winner], key=_relation_tournament_sort_key):
        decision = _relation_pair_decision(
            winner,
            challenger,
            correlation_config,
            near_duplicate_tolerance=near_duplicate_tolerance,
        )
        if decision is None:
            pair_winner = _regular_winner_for_cluster([winner, challenger], correlation_config)
            if pair_winner is not winner:
                winner = pair_winner
            continue
        applied_relation_rule = True
        _apply_relation_audit(decision)
        winner = decision["winner"]

    if not applied_relation_rule:
        return _regular_winner_for_cluster(rows, correlation_config)
    return winner


def _annotate_score(candidate: dict[str, Any], correlation_config: dict[str, Any]) -> None:
    candidate["market_family"] = candidate.get("market_family") or market_family(candidate)
    annotate_entry_quality(candidate)
    candidate["selection_safety_bonus"] = selection_safety_bonus(candidate)
    candidate["odds_quality_bonus"] = odds_quality_bonus(candidate)
    candidate["portfolio_risk_penalty"] = risk_penalty(candidate)
    candidate["portfolio_selection_score"] = portfolio_selection_score(candidate, correlation_config)
    candidate.setdefault("correlation_cluster_key", correlation_cluster_key(candidate))
    candidate.setdefault("correlation_strength", "low")
    candidate.setdefault("correlation_reason", "")
    candidate.setdefault("portfolio_rank_within_cluster", 1)
    candidate.setdefault("selected_over_candidate_id", "")
    for field in RELATION_AUDIT_FIELDS:
        candidate.setdefault(field, "")


def _apply_hard_correlation_clusters(
    group: list[dict[str, Any]],
    *,
    near_duplicate_tolerance: float,
    contradictory_tolerance: float,
    correlation_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(group) <= 1 or not _is_enabled(correlation_config.get("enabled", True)):
        for candidate in group:
            candidate.setdefault("correlation_cluster_key", correlation_cluster_key(candidate))
        return group, []

    parent = list(range(len(group)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    pair_details: dict[tuple[int, int], dict[str, str]] = {}
    for left_idx in range(len(group)):
        for right_idx in range(left_idx + 1, len(group)):
            detail = classify_correlation_detail(
                group[left_idx],
                group[right_idx],
                near_duplicate_tolerance=near_duplicate_tolerance,
                contradictory_tolerance=contradictory_tolerance,
            )
            pair_details[(left_idx, right_idx)] = detail
            if detail["strength"] in HARD_CORRELATION_STRENGTHS:
                union(left_idx, right_idx)

    components: dict[int, list[int]] = {}
    for idx in range(len(group)):
        components.setdefault(find(idx), []).append(idx)

    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for indexes in components.values():
        rows = [group[idx] for idx in indexes]
        if len(rows) == 1:
            row = rows[0]
            row["correlation_cluster_key"] = correlation_cluster_key(row)
            row.setdefault("portfolio_rank_within_cluster", 1)
            kept.append(row)
            continue

        hard_details = [
            pair_details[(min(left, right), max(left, right))]
            for left in indexes
            for right in indexes
            if left < right and pair_details[(left, right)]["strength"] in HARD_CORRELATION_STRENGTHS
        ]
        cluster_strength = max((detail["strength"] for detail in hard_details), key=_strength_rank, default="high")
        cluster_reasons = {detail["reason"] for detail in hard_details if detail.get("reason")}
        cluster_key = _component_cluster_key(rows, cluster_reasons)
        winner = _winner_for_cluster(rows, correlation_config, near_duplicate_tolerance=near_duplicate_tolerance)
        try:
            max_keep = max(1, int(correlation_config.get("max_picks_per_high_correlation_cluster", 1)))
        except (TypeError, ValueError):
            max_keep = 1

        ordered_rows = [winner] + [row for row in sorted(rows, key=_portfolio_score_sort_key) if row is not winner]
        index_by_identity = {id(group[idx]): idx for idx in indexes}
        for rank, row in enumerate(ordered_rows, start=1):
            row["correlation_cluster_key"] = cluster_key
            row["portfolio_rank_within_cluster"] = rank
            row.setdefault("selected_over_candidate_id", "")
            row_strength = cluster_strength
            row_reason = "+".join(sorted(cluster_reasons))
            if rank > max_keep:
                row_idx = index_by_identity[id(row)]
                winner_idx = index_by_identity[id(winner)]
                direct = pair_details.get((min(row_idx, winner_idx), max(row_idx, winner_idx)), {"strength": "low", "reason": ""})
                if direct["strength"] in HARD_CORRELATION_STRENGTHS:
                    row_strength = direct["strength"]
                    row_reason = direct["reason"]
                row["correlation_strength"] = row_strength
                row["correlation_reason"] = row_reason
                row["selected_over_candidate_id"] = winner.get("bet_id") or ""
                rejected.append(
                    _candidate_to_rejection(
                        row,
                        _portfolio_reject_reason(row_strength),
                        related_bet_id=winner.get("bet_id"),
                        details=(
                            f"score={row.get('portfolio_selection_score')}|"
                            f"selected_score={winner.get('portfolio_selection_score')}|"
                            f"correlation_reason={row_reason}"
                            f"{_relation_audit_details(row)}"
                        ),
                        scope="match_correlation_cluster",
                    )
                )
            else:
                row["correlation_strength"] = cluster_strength
                row["correlation_reason"] = row_reason
                kept.append(row)

    return kept, rejected


def select_top_picks(candidates: Iterable[Mapping[str, Any]], return_meta: bool = False):
    candidate_rows = [dict(candidate) for candidate in candidates]
    if not candidate_rows:
        return ([], []) if return_meta else []

    runtime = get_runtime_config()
    portfolio_rules = runtime.rules.get("portfolio", {})
    try:
        max_picks_per_match = int(portfolio_rules.get("max_picks_per_match", 2))
    except (TypeError, ValueError):
        max_picks_per_match = 2
    correlation_config = merge_correlation_selection_config(portfolio_rules.get("correlation_selection", {}))

    for candidate in candidate_rows:
        candidate.setdefault("portfolio_line_role", "standard")
        candidate.setdefault("selection_policy_status", "selection_pending")
        _annotate_score(candidate, correlation_config)

    rejections: list[dict[str, Any]] = []
    selected_count_by_scope: dict[tuple[str, str], int] = {}
    selected_stake_by_scope: dict[tuple[str, str], float] = {}
    near_duplicate_tolerance = float(portfolio_rules.get("near_duplicate_line_tolerance", 0.25))
    contradictory_tolerance = float(portfolio_rules.get("contradictory_line_tolerance", 0.25))
    medium_correlation_policy = str(portfolio_rules.get("medium_correlation_policy", "downgrade"))

    kept_rows: list[dict[str, Any]] = []
    for raw_group in _group_by_match(candidate_rows):
        group, ladder_rejections = _apply_asian_total_line_ladder(raw_group)
        for row in group:
            _annotate_score(row, correlation_config)
        for rejected in ladder_rejections:
            _annotate_score(rejected, correlation_config)
        rejections.extend(ladder_rejections)
        group, correlation_rejections = _apply_hard_correlation_clusters(
            group,
            near_duplicate_tolerance=near_duplicate_tolerance,
            contradictory_tolerance=contradictory_tolerance,
            correlation_config=correlation_config,
        )
        rejections.extend(correlation_rejections)
        group = sorted(group, key=_portfolio_score_sort_key)

        selected: list[dict[str, Any]] = []
        for row in group:
            candidate = dict(row)
            _annotate_score(candidate, correlation_config)

            if len(selected) >= max_picks_per_match:
                rejections.append(_candidate_to_rejection(candidate, "MATCH_PICK_CAP_REACHED", related_bet_id=selected[0].get("bet_id"), scope="match"))
                continue

            highest_level = "low"
            highest_reason = ""
            primary_ref = None
            skip = False
            for existing in selected:
                detail = classify_correlation_detail(
                    existing,
                    candidate,
                    near_duplicate_tolerance=near_duplicate_tolerance,
                    contradictory_tolerance=contradictory_tolerance,
                )
                level = detail["strength"]
                if level in HARD_CORRELATION_STRENGTHS:
                    candidate["correlation_strength"] = level
                    candidate["correlation_reason"] = detail["reason"]
                    candidate["selected_over_candidate_id"] = existing.get("bet_id") or ""
                    rejections.append(
                        _candidate_to_rejection(
                            candidate,
                            _portfolio_reject_reason(level),
                            related_bet_id=existing.get("bet_id"),
                            details=(
                                f"score={candidate.get('portfolio_selection_score')}|"
                                f"selected_score={existing.get('portfolio_selection_score')}|"
                                f"correlation_reason={detail['reason']}"
                                f"{_relation_audit_details(candidate)}"
                            ),
                            scope="match_correlation_cluster",
                        )
                    )
                    skip = True
                    break
                if level == "medium":
                    highest_level = "medium"
                    highest_reason = detail["reason"]
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
                candidate["stake_units"] = min(float(candidate.get("stake_units") or 0.0), 0.5)
                candidate["risk_flags"] = _append_flag(candidate.get("risk_flags", "SEM_FLAG"), "CORRELACAO_JOGO")
                _annotate_score(candidate, correlation_config)
                candidate["correlation_level"] = "medium"
                candidate["correlation_strength"] = "medium"
                candidate["correlation_reason"] = highest_reason
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
            _record_exposure(candidate, selected_count_by_scope, selected_stake_by_scope, portfolio_rules)
            selected.append(candidate)

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
