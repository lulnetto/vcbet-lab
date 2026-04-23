from __future__ import annotations

from hashlib import md5
from typing import Any

from config_ligas import liga_eh_caotica
from market_thresholds import (
    get_allowed_markets,
    get_confidence_caps,
    get_confidence_penalties,
    get_critical_flags,
    get_market_priority,
    get_market_threshold,
    get_primary_markets,
)
from strategy_config import get_runtime_config


def is_xg_fallback(xg_row: Any) -> bool:
    try:
        return (
            float(xg_row["xg_home"]) == float(xg_row["xg"])
            and float(xg_row["xg_away"]) == float(xg_row["xg"])
            and float(xg_row["xga_home"]) == float(xg_row["xga"])
            and float(xg_row["xga_away"]) == float(xg_row["xga"])
        )
    except Exception:
        return True


def build_bet_id(run_id: str, match_name: str, market_type: str, selection_raw: str, odd_entrada: float) -> str:
    raw = f"{run_id}|{match_name}|{market_type}|{selection_raw}|{odd_entrada:.4f}"
    return md5(raw.encode("utf-8")).hexdigest()[:12]


def _line_extreme(market_type: str, line: float | None) -> bool:
    if line is None:
        return False
    abs_line = abs(float(line))
    if market_type in {"total_goals", "asian_total"}:
        return line <= 1.0 or line >= 4.0
    if market_type == "team_total":
        return line <= 0.5 or line >= 3.0
    if market_type == "asian_handicap":
        return abs_line > 1.0
    return False


def _base_risk_flags(candidate: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    market_type = candidate["market_type"]
    line = candidate.get("line")
    odd = float(candidate["odd_entrada"])
    mu_total = float(candidate["mu_total"])
    thresholds = get_market_threshold(market_type)

    home_status = candidate.get("match_status_home")
    away_status = candidate.get("match_status_away")
    if home_status not in {"auto_exact", "manual_approved", "auto_fuzzy_high"} or away_status not in {"auto_exact", "manual_approved", "auto_fuzzy_high"}:
        flags.append("MATCH_DUVIDOSO")
    elif home_status == "auto_fuzzy_high" or away_status == "auto_fuzzy_high":
        flags.append("MATCH_FUZZY")

    if candidate.get("xg_fallback_home") or candidate.get("xg_fallback_away"):
        flags.append("FALLBACK_XG_GLOBAL")
        if market_type in {"team_total", "asian_handicap"}:
            flags.append("DADO_INCOMPLETO_LIGA")

    if liga_eh_caotica(str(candidate.get("league", ""))):
        flags.append("LIGA_VOLATIL")

    if market_type == "team_total":
        flags.append("MERCADO_TIME")

    if _line_extreme(market_type, line):
        flags.append("LINHA_EXTREMA")

    if odd > thresholds.standard_max:
        flags.append("ODD_ALTA_VARIANCIA")

    if market_type == "asian_handicap" and line is not None:
        abs_line = abs(float(line))
        if abs_line in {0.0, 0.25}:
            flags.append("DRAW_SENSITIVE_LINE")
        if abs_line >= 1.0:
            flags.append("HEAVY_FAVORITE_LINE")
            flags.append("POISSON_MARGIN_RISK")

    if mu_total <= 2.1:
        flags.append("LOW_SCORE_MATCH")
    if mu_total >= 3.9:
        flags.append("HIGH_TOTAL_MATCH")

    return sorted(set(flags))


def _confidence_score(candidate: dict[str, Any], flags: list[str]) -> tuple[int, list[str], int | None]:
    runtime = get_runtime_config()
    rules = runtime.rules
    bonuses = rules.get("bonuses", {})
    score = 0
    reasons: list[str] = []
    ev_decimal = float(candidate["ev_decimal"])
    market_type = candidate["market_type"]
    thresholds = get_market_threshold(market_type)

    if ev_decimal >= float(rules.get("very_strong_edge", 0.14)):
        score += 3
        reasons.append("EDGE_FORTE")
    elif ev_decimal >= thresholds.edge_strong:
        score += 2
        reasons.append("EDGE_FORTE")
    elif ev_decimal >= thresholds.edge_min:
        score += 1
        reasons.append("EDGE_MODERADO")

    if market_type in get_primary_markets():
        score += int(bonuses.get("primary_market", 1))
        reasons.append("MERCADO_PRINCIPAL")

    if "DADO_INCOMPLETO_LIGA" not in flags and "FALLBACK_XG_GLOBAL" not in flags:
        score += int(bonuses.get("complete_data", 1))
        reasons.append("DADO_COMPLETO")

    if candidate.get("match_status_home") in {"auto_exact", "manual_approved"} and candidate.get("match_status_away") in {"auto_exact", "manual_approved"}:
        score += int(bonuses.get("reliable_match", 1))
        reasons.append("MATCH_CONFIAVEL")

    if not liga_eh_caotica(str(candidate.get("league", ""))):
        score += int(bonuses.get("stable_league", 1))
        reasons.append("LIGA_ESTAVEL")

    if not flags:
        score += int(bonuses.get("clean_setup", 1))
        reasons.append("SETUP_LIMPO")

    penalties = get_confidence_penalties()
    for flag in flags:
        score -= penalties.get(flag, 0)

    score = max(0, min(5, score))

    cap_value = None
    for flag in flags:
        if flag in get_confidence_caps():
            value = get_confidence_caps()[flag]
            cap_value = value if cap_value is None else min(cap_value, value)
    if cap_value is not None:
        score = min(score, cap_value)

    return score, reasons, cap_value


def evaluate_pick_candidate_with_meta(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    market_type = candidate["market_type"]
    if market_type not in get_allowed_markets():
        return None, "unsupported_market"

    runtime = get_runtime_config()
    thresholds = get_market_threshold(market_type)
    odd = float(candidate["odd_entrada"])
    ev_decimal = float(candidate["ev_decimal"])

    if odd < thresholds.odd_min or odd > thresholds.extended_max:
        return None, "odd_out_of_range"
    if ev_decimal < thresholds.edge_min:
        return None, "edge_below_min"

    flags = _base_risk_flags(candidate)
    confidence_score, reasons, cap_value = _confidence_score(candidate, flags)

    critical_present = bool(get_critical_flags().intersection(flags))
    in_extended = odd > thresholds.standard_max

    ext_rules = runtime.rules.get("extended_range", {})
    if in_extended and ext_rules.get("enabled", True):
        if ev_decimal < thresholds.edge_premium_extended:
            return None, "extended_range_requires_premium_signal"
        if confidence_score < int(ext_rules.get("min_confidence", 5)):
            return None, "extended_range_requires_premium_signal"
        if ext_rules.get("require_no_critical_flags", True) and critical_present:
            return None, "extended_range_requires_premium_signal"
        if ext_rules.get("require_no_flags", True) and flags:
            return None, "extended_range_requires_premium_signal"

    conf_rules = runtime.rules.get("confidence", {})
    stakes = runtime.rules.get("stakes", {})
    min_to_keep = int(conf_rules.get("min_to_keep", 3))
    full_unit_min = int(conf_rules.get("full_unit_min", 5))
    if critical_present or confidence_score < min_to_keep:
        stake_units = float(stakes.get("zero_unit", 0.0))
    elif (
        confidence_score >= full_unit_min
        and (not conf_rules.get("full_unit_requires_no_flags", True) or not flags)
        and ev_decimal >= thresholds.edge_strong
        and (not conf_rules.get("full_unit_requires_not_extended", True) or not in_extended)
    ):
        stake_units = float(stakes.get("full_unit", 1.0))
    else:
        stake_units = float(stakes.get("half_unit", 0.5))

    if stake_units <= 0:
        return None, "low_confidence_or_critical_flag"

    fair_odd = candidate.get("odd_justa")
    fair_odd = round(float(fair_odd), 2) if fair_odd else None

    market_priority = get_market_priority()
    return {
        **candidate,
        "bet_id": build_bet_id(
            candidate["run_id"],
            candidate["match_name"],
            candidate["market_type"],
            candidate["selection_raw"],
            candidate["odd_entrada"],
        ),
        "odd_justa": fair_odd,
        "ev_percent": round(ev_decimal * 100, 2),
        "confidence_score": confidence_score,
        "confidence_cap": cap_value,
        "stake_units": stake_units,
        "entry_reason": "|".join(reasons[:4]) if reasons else "SEM_MOTIVO",
        "risk_flags": "|".join(flags) if flags else "SEM_FLAG",
        "market_priority": market_priority.get(market_type, 99),
        "strategy_config_name": runtime.name,
        "strategy_config_fingerprint": runtime.fingerprint,
    }, None


def evaluate_pick_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    evaluated, _ = evaluate_pick_candidate_with_meta(candidate)
    return evaluated
