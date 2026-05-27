from __future__ import annotations

from typing import Any

from vcbet.core.selection.entry_quality import compute_entry_quality


HARD_CORRELATION_STRENGTHS = {"equivalent", "near_duplicate", "high", "contradictory"}
TOTAL_PROTECTED_RELATION_KEYS = {"TOTAL_OVER_PROTECTED_LINE", "TOTAL_UNDER_PROTECTED_LINE"}
TOTAL_RELATION_KEYS = TOTAL_PROTECTED_RELATION_KEYS | {"TOTAL_EQUALS_ASIAN_TOTAL"}

DEFAULT_CORRELATION_SELECTION_CONFIG: dict[str, Any] = {
    "enabled": True,
    "max_picks_per_high_correlation_cluster": 1,
    "ev_gap_override_pp": 2.0,
    "ev_gap_override_by_relation": {
        "DNB_EQUALS_AH_0": 0.0,
        "DNB_AH_PLUS_0_25": 4.0,
        "DNB_AH_PLUS_0_5": 6.0,
        "DNB_AH_MINUS_0_25": 2.0,
        "AH_NEAR_DUPLICATE_LINE": 2.0,
        "BTTS_YES_TEAM_TOTAL_OVER_0_5": 5.0,
        "TOTAL_EQUALS_ASIAN_TOTAL": 0.0,
    },
    "total_line_ev_gap_override_by_distance": {
        "0.25": 3.0,
        "0.5": 5.0,
        "0.75": 6.0,
        "1.0": 7.0,
    },
    "total_line_default_ev_gap_override_pp": 5.0,
    "score_weights": {
        "ev_percent": 1.0,
        "confidence_score": 0.75,
        "entry_quality_score": 0.15,
        "market_priority": 0.75,
        "selection_safety": 0.75,
        "odds_quality": 0.25,
        "risk_penalty": 1.0,
    },
    "market_priority": {
        "draw_no_bet": 5,
        "asian_handicap": 5,
        "asian_total": 4,
        "total_goals": 4,
        "team_total": 3,
        "btts": 3,
    },
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except (TypeError, ValueError):
        pass
    return " ".join(str(value).strip().casefold().split())


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    if str(value).strip().lower() in {"", "nan", "none", "<na>"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_or_default(value: Any, default: float = 0.0) -> float:
    parsed = _num(value)
    return default if parsed is None else parsed


def _market_family(candidate: dict[str, Any]) -> str:
    explicit = _clean(candidate.get("market_family"))
    if explicit:
        return explicit
    market_type = _clean(candidate.get("market_type"))
    if market_type in {"total_goals", "asian_total"}:
        return "goals_total"
    if market_type == "team_total":
        return "team_goals"
    if market_type == "asian_handicap":
        return "handicap"
    if market_type == "btts":
        return "btts"
    return market_type or "unknown"


def _same_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    match_a = _clean(a.get("match_name"))
    match_b = _clean(b.get("match_name"))
    if match_a and match_b:
        return match_a == match_b
    return True


def _same_target(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        _clean(a.get("target_team_role") or "geral") == _clean(b.get("target_team_role") or "geral")
        and _clean(a.get("target_team_name") or "geral") == _clean(b.get("target_team_name") or "geral")
    )


def _same_side_target(a: dict[str, Any], b: dict[str, Any]) -> bool:
    side_a = _clean(a.get("side"))
    side_b = _clean(b.get("side"))
    if not side_a or side_a != side_b:
        return False
    if _same_target(a, b):
        return True
    role_a = _clean(a.get("target_team_role"))
    role_b = _clean(b.get("target_team_role"))
    return role_a == side_a and role_b == side_b


def _line_gap(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    line_a = _num(a.get("line"))
    line_b = _num(b.get("line"))
    if line_a is None or line_b is None:
        return None
    return abs(line_a - line_b)


def _handicap_opposition_gap(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    line_a = _num(a.get("line"))
    line_b = _num(b.get("line"))
    if line_a is None or line_b is None:
        return None
    return min(abs(line_a - line_b), abs(line_a + line_b))


def _detail(strength: str = "low", reason: str = "") -> dict[str, str]:
    return {"strength": strength, "reason": reason}


def _is_protected_ah_line(line: float | None) -> bool:
    if line is None:
        return False
    return any(abs(line - target) < 1e-9 for target in {0.25, 0.5, -0.25})


def _total_goals_asian_total_key(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    line_tolerance: float = 0.01,
) -> str | None:
    mt_a = _clean(a.get("market_type"))
    mt_b = _clean(b.get("market_type"))
    if {mt_a, mt_b} != {"total_goals", "asian_total"}:
        return None
    if not _same_target(a, b):
        return None

    side_a = _clean(a.get("side"))
    side_b = _clean(b.get("side"))
    if side_a != side_b or side_a not in {"over", "under"}:
        return None

    line_a = _num(a.get("line"))
    line_b = _num(b.get("line"))
    if line_a is None or line_b is None:
        return "TOTAL_GOALS_ASIAN_TOTAL_SAME_SIDE"
    if abs(line_a - line_b) <= line_tolerance:
        return "TOTAL_EQUALS_ASIAN_TOTAL"
    if side_a == "over":
        return "TOTAL_OVER_PROTECTED_LINE"
    return "TOTAL_UNDER_PROTECTED_LINE"


def classify_correlation_detail(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    near_duplicate_tolerance: float = 0.25,
    contradictory_tolerance: float = 0.25,
) -> dict[str, str]:
    mt_a = _clean(a.get("market_type"))
    mt_b = _clean(b.get("market_type"))
    side_a = _clean(a.get("side"))
    side_b = _clean(b.get("side"))
    line_a = _num(a.get("line"))
    line_b = _num(b.get("line"))

    if not _same_match(a, b):
        return _detail()

    pair = {mt_a, mt_b}

    if pair == {"total_goals", "asian_total"}:
        total_relation = _total_goals_asian_total_key(a, b)
        if total_relation == "TOTAL_EQUALS_ASIAN_TOTAL":
            return _detail("equivalent", total_relation)
        if total_relation in TOTAL_PROTECTED_RELATION_KEYS:
            return _detail("high", total_relation)
        if total_relation == "TOTAL_GOALS_ASIAN_TOTAL_SAME_SIDE":
            return _detail("high", total_relation)

    if pair == {"draw_no_bet", "asian_handicap"} and _same_side_target(a, b):
        ah = a if mt_a == "asian_handicap" else b
        ah_line = _num(ah.get("line"))
        if ah_line is not None and abs(ah_line) < 1e-9:
            return _detail("equivalent", "DNB_EQUALS_AH_0")
        if _is_protected_ah_line(ah_line):
            return _detail("high", "DNB_AH_SAME_SIDE")

    if mt_a == mt_b == "asian_handicap" and _same_side_target(a, b):
        gap = _line_gap(a, b)
        if gap is not None and gap <= near_duplicate_tolerance:
            return _detail("near_duplicate", "AH_NEAR_DUPLICATE_LINE")

    if mt_a == mt_b:
        family = _market_family(a)
        same_target = _same_target(a, b)
        if mt_a == "draw_no_bet" and side_a != side_b and side_a and side_b:
            return _detail("contradictory", "DNB_OPPOSITE_SIDE")
        if family in {"goals_total", "team_goals"}:
            if {side_a, side_b} == {"over", "under"}:
                if family != "team_goals" or same_target:
                    gap = _line_gap(a, b)
                    if gap is not None and gap <= contradictory_tolerance:
                        return _detail("contradictory", "OPPOSITE_TOTAL_SIDE_SAME_LINE")
            if side_a == side_b and (family != "team_goals" or same_target):
                gap = _line_gap(a, b)
                if gap is not None and gap <= near_duplicate_tolerance:
                    return _detail("near_duplicate", "TOTAL_NEAR_DUPLICATE_LINE")

        if family == "btts":
            if {side_a, side_b} == {"yes", "no"}:
                return _detail("contradictory", "BTTS_YES_NO")
            if side_a == side_b:
                return _detail("near_duplicate", "BTTS_SAME_SELECTION")

        if family == "handicap":
            if side_a != side_b and side_a and side_b:
                gap = _handicap_opposition_gap(a, b)
                if gap is None or gap <= contradictory_tolerance:
                    return _detail("contradictory", "OPPOSITE_HANDICAP_SIDE_NEAR_LINE")
            if side_a == side_b and same_target:
                gap = _line_gap(a, b)
                if gap is not None and gap <= near_duplicate_tolerance:
                    return _detail("near_duplicate", "AH_NEAR_DUPLICATE_LINE")

        if side_a == side_b and same_target:
            if line_a is None or line_b is None:
                same_raw = _clean(a.get("selection_raw")) == _clean(b.get("selection_raw"))
                if same_raw:
                    return _detail("near_duplicate", "SAME_SELECTION")
            else:
                gap = _line_gap(a, b)
                if gap is not None and gap <= near_duplicate_tolerance:
                    return _detail("near_duplicate", "NEAR_DUPLICATE_LINE")
        return _detail("medium", "SAME_MARKET_FAMILY")

    if pair == {"btts", "team_total"}:
        team = a if mt_a == "team_total" else b
        btts = a if mt_a == "btts" else b
        team_line = _num(team.get("line"))
        if _clean(btts.get("side")) == "yes" and _clean(team.get("side")) == "over" and (team_line is not None and team_line <= 0.5):
            return _detail("high", "BTTS_YES_TEAM_TOTAL_OVER_0_5")
        if _clean(btts.get("side")) == "no" and _clean(team.get("side")) == "under" and (team_line is not None and team_line <= 0.5):
            return _detail("high", "BTTS_NO_TEAM_TOTAL_UNDER_0_5")
        return _detail("medium", "BTTS_TEAM_TOTAL_RELATED")

    if "btts" in pair and pair.intersection({"total_goals", "asian_total"}):
        total = a if mt_a in {"total_goals", "asian_total"} else b
        btts = a if mt_a == "btts" else b
        if _clean(total.get("side")) == "over" and _clean(btts.get("side")) == "yes":
            return _detail("medium", "TOTAL_OVER_BTTS_YES")
        if _clean(total.get("side")) == "under" and _clean(btts.get("side")) == "no":
            return _detail("medium", "TOTAL_UNDER_BTTS_NO")
        return _detail("medium", "TOTAL_BTTS_RELATED")

    if "team_total" in pair and pair.intersection({"total_goals", "asian_total"}):
        total = a if mt_a in {"total_goals", "asian_total"} else b
        team = a if mt_a == "team_total" else b
        if _clean(team.get("side")) == "over" and _clean(total.get("side")) == "over":
            return _detail("medium", "TEAM_TOTAL_OVER_TOTAL_OVER")
        if _clean(team.get("side")) == "under" and _clean(total.get("side")) == "under":
            return _detail("medium", "TEAM_TOTAL_UNDER_TOTAL_UNDER")
        return _detail("medium", "TEAM_TOTAL_TOTAL_RELATED")

    if pair == {"total_goals", "asian_total"}:
        gap = _line_gap(a, b)
        if side_a == side_b and gap is not None and gap <= near_duplicate_tolerance:
            return _detail("near_duplicate", "TOTAL_NEAR_DUPLICATE_LINE")
        return _detail("medium", "TOTAL_MARKETS_RELATED")

    if "asian_handicap" in pair and pair.intersection({"team_total", "total_goals", "asian_total", "btts"}):
        return _detail("medium", "HANDICAP_GOALS_RELATED")

    return _detail()


def relation_override_key(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    near_duplicate_tolerance: float = 0.25,
    line_tolerance: float = 0.01,
) -> str | None:
    mt_a = _clean(a.get("market_type"))
    mt_b = _clean(b.get("market_type"))

    if not _same_match(a, b):
        return None

    pair = {mt_a, mt_b}
    total_relation = _total_goals_asian_total_key(a, b, line_tolerance=line_tolerance)
    if total_relation in TOTAL_RELATION_KEYS:
        return total_relation

    if pair == {"draw_no_bet", "asian_handicap"} and _same_side_target(a, b):
        ah = a if mt_a == "asian_handicap" else b
        ah_line = _num(ah.get("line"))
        if ah_line is None:
            return None
        if abs(ah_line) <= line_tolerance:
            return "DNB_EQUALS_AH_0"
        if abs(ah_line - 0.25) <= line_tolerance:
            return "DNB_AH_PLUS_0_25"
        if abs(ah_line - 0.5) <= line_tolerance:
            return "DNB_AH_PLUS_0_5"
        if abs(ah_line + 0.25) <= line_tolerance:
            return "DNB_AH_MINUS_0_25"
        return None

    if mt_a == mt_b == "asian_handicap" and _same_side_target(a, b):
        gap = _line_gap(a, b)
        if gap is not None and gap <= near_duplicate_tolerance:
            return "AH_NEAR_DUPLICATE_LINE"
        return None

    if pair == {"btts", "team_total"}:
        team = a if mt_a == "team_total" else b
        btts = a if mt_a == "btts" else b
        team_line = _num(team.get("line"))
        if _clean(btts.get("side")) == "yes" and _clean(team.get("side")) == "over" and team_line is not None and team_line <= 0.5:
            return "BTTS_YES_TEAM_TOTAL_OVER_0_5"

    return None


def classify_correlation(a: dict[str, Any], b: dict[str, Any]) -> str:
    detail = classify_correlation_detail(a, b)
    strength = detail["strength"]
    if strength in HARD_CORRELATION_STRENGTHS:
        return "high"
    return strength


def correlation_cluster_key(candidate: dict[str, Any]) -> str:
    parts = [
        _text(candidate.get("match_name")),
        _text(candidate.get("market_type")),
        _text(candidate.get("market_family") or _market_family(candidate)),
        _text(candidate.get("side")),
        _text(candidate.get("target_team_role") or "geral"),
        _text(candidate.get("target_team_name") or "geral"),
        _text(candidate.get("line")),
        _text(candidate.get("selection_raw")),
    ]
    return "|".join(part if part else "-" for part in parts)


def merge_correlation_selection_config(config: dict[str, Any] | None) -> dict[str, Any]:
    merged = {
        **DEFAULT_CORRELATION_SELECTION_CONFIG,
        "ev_gap_override_by_relation": dict(DEFAULT_CORRELATION_SELECTION_CONFIG["ev_gap_override_by_relation"]),
        "total_line_ev_gap_override_by_distance": dict(DEFAULT_CORRELATION_SELECTION_CONFIG["total_line_ev_gap_override_by_distance"]),
        "score_weights": dict(DEFAULT_CORRELATION_SELECTION_CONFIG["score_weights"]),
        "market_priority": dict(DEFAULT_CORRELATION_SELECTION_CONFIG["market_priority"]),
    }
    if not isinstance(config, dict):
        return merged
    for key, value in config.items():
        if key in {"ev_gap_override_by_relation", "total_line_ev_gap_override_by_distance", "score_weights", "market_priority"} and isinstance(value, dict):
            child = dict(merged[key])
            child.update(value)
            merged[key] = child
        else:
            merged[key] = value
    return merged


def selection_safety_bonus(candidate: dict[str, Any]) -> float:
    market_type = _clean(candidate.get("market_type"))
    side = _clean(candidate.get("side"))
    line = _num(candidate.get("line"))

    if market_type == "draw_no_bet":
        return 3.0
    if market_type == "asian_handicap":
        if line is None:
            return 2.0
        if abs(line - 0.5) < 1e-9:
            return 4.0
        if abs(line - 0.25) < 1e-9:
            return 3.5
        if abs(line) < 1e-9:
            return 3.0
        if abs(line + 0.25) < 1e-9:
            return 2.0
        if abs(line + 0.5) < 1e-9:
            return 1.5
        return 2.0
    if market_type == "team_total":
        if side == "over" and line is not None and line <= 0.5:
            return 3.0
        if side == "under" and line is not None and line <= 1.5:
            return 2.5
        return 2.0
    if market_type == "btts":
        return 2.0 if side == "yes" else 1.5
    if market_type in {"total_goals", "asian_total"}:
        if line is not None and 1.5 <= line <= 3.0:
            return 2.0
        return 1.0
    return 1.0


def odds_quality_bonus(candidate: dict[str, Any]) -> float:
    odd = _num(candidate.get("odd_entrada"))
    if odd is None:
        odd = _num(candidate.get("odd"))
    if odd is None:
        return 0.0
    if 1.70 <= odd <= 2.40:
        return 1.0
    if 2.40 < odd <= 2.80:
        return 0.3
    if odd > 2.80:
        return -0.5
    if odd < 1.60:
        return -0.5
    return 0.0


def risk_penalty(candidate: dict[str, Any]) -> float:
    raw_flags = _text(candidate.get("risk_flags"))
    if not raw_flags or raw_flags.strip().upper() == "SEM_FLAG":
        return 0.0
    flags = [flag for flag in raw_flags.split("|") if flag and flag.strip().upper() != "SEM_FLAG"]
    return float(len(flags)) * 0.5


def portfolio_selection_score(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> float:
    cfg = merge_correlation_selection_config(config)
    weights = cfg["score_weights"]
    market_priority = cfg["market_priority"]
    market_type = _text(candidate.get("market_type"))

    ev_percent = _num_or_default(candidate.get("ev_percent"))
    confidence = _num_or_default(candidate.get("confidence_score"))
    entry_quality = _num(candidate.get("entry_quality_score"))
    if entry_quality is None:
        entry_quality = _num_or_default(compute_entry_quality(candidate).get("entry_quality_score"))
    priority = _num_or_default(market_priority.get(market_type), 0.0)
    safety = selection_safety_bonus(candidate)
    odds_quality = odds_quality_bonus(candidate)
    risk = risk_penalty(candidate)
    ev_weight = float(weights.get("ev_percent", 1.0))
    try:
        from vcbet.core.strategy_config import get_runtime_config

        ev_policy = get_runtime_config().ev_policy
        cap = _num(ev_policy.get("cap_ev_score_contribution")) if isinstance(ev_policy, dict) else None
        if cap is not None:
            ev_weight = min(ev_weight, cap)
        elif isinstance(ev_policy, dict) and ev_policy.get("use_as_ranker") is False:
            ev_weight = 0.0
    except Exception:
        pass

    return round(
        ev_percent * ev_weight
        + confidence * float(weights.get("confidence_score", 0.75))
        + entry_quality * float(weights.get("entry_quality_score", 0.15))
        + priority * float(weights.get("market_priority", 0.75))
        + safety * float(weights.get("selection_safety", 0.75))
        + odds_quality * float(weights.get("odds_quality", 0.25))
        - risk * float(weights.get("risk_penalty", 1.0)),
        6,
    )
