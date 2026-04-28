from __future__ import annotations

from hashlib import md5
from typing import Any

from vcbet.core.config_ligas import liga_eh_caotica
from vcbet.core.market_thresholds import (
    get_allowed_markets,
    get_confidence_caps,
    get_confidence_penalties,
    get_critical_flags,
    get_market_priority,
    get_market_threshold,
    get_primary_markets,
)
from vcbet.core.risk_policy import assess_risk_flags, safety_gate_flags
from vcbet.core.strategy_config import get_runtime_config


PRICING_SIGNAL_TYPE = "model_derived_not_calibrated"
CONFIDENCE_SCORE_TYPE = "heuristic_operational"
CONFIDENCE_SCORE_SCALE = "0-5"


def _normalize_identity_part(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return " ".join(text.split())


def build_bet_id(
    match_datetime: str,
    league: str,
    home_team: str,
    away_team: str,
    market_type: str,
    market_scope: str,
    side: str | None,
    line: float | None,
    target_team_role: str | None,
    target_team_name: str | None,
    selection_raw: str,
) -> str:
    """Identidade estável da aposta, independente de run/config/odd."""
    line_part = "" if line is None else f"{float(line):.2f}"
    raw = "|".join(
        _normalize_identity_part(part)
        for part in [
            match_datetime,
            league,
            home_team,
            away_team,
            market_type,
            market_scope,
            side,
            line_part,
            target_team_role or "geral",
            target_team_name or "geral",
            selection_raw,
        ]
    )
    return md5(raw.encode("utf-8")).hexdigest()[:12]


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

    if candidate.get("match_status_home") in {"auto_exact", "manual_approved", "MATCH_REGISTRY_APPROVED"} and candidate.get("match_status_away") in {"auto_exact", "manual_approved", "MATCH_REGISTRY_APPROVED"}:
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


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return build_bet_id(
        candidate["match_datetime"],
        candidate["league"],
        candidate["home_team"],
        candidate["away_team"],
        candidate["market_type"],
        candidate["market_scope"],
        candidate.get("side"),
        candidate.get("line"),
        candidate.get("target_team_role"),
        candidate.get("target_team_name"),
        candidate["selection_raw"],
    )


def _rejected_candidate_payload(
    candidate: dict[str, Any],
    *,
    reject_reason: str,
    flags: list[str] | None = None,
    confidence_score: int | None = None,
    confidence_cap: int | None = None,
    safety_gate_flags: list[str] | None = None,
) -> dict[str, Any]:
    safety_gate_flags = safety_gate_flags or []
    flags = flags or []
    return {
        **candidate,
        "bet_id": _candidate_identity(candidate),
        "pricing_signal_type": PRICING_SIGNAL_TYPE,
        "confidence_score": confidence_score,
        "confidence_score_type": CONFIDENCE_SCORE_TYPE,
        "confidence_score_scale": CONFIDENCE_SCORE_SCALE,
        "confidence_cap": confidence_cap,
        "risk_flags": "|".join(flags) if flags else "SEM_FLAG",
        "pick_safety_status": "blocked" if safety_gate_flags else "rejected",
        "candidate_stage": "blocked_unsafe_candidate" if safety_gate_flags else "rejected_candidate",
        "decision_policy_status": "blocked_by_risk_policy" if safety_gate_flags else "rejected",
        "decision_reject_reason": reject_reason,
        "safety_gate_reason": "|".join(safety_gate_flags),
        "safety_reject_reason": reject_reason,
    }


def evaluate_pick_candidate_with_details(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    market_type = candidate["market_type"]
    if market_type not in get_allowed_markets():
        return None, "unsupported_market", None

    runtime = get_runtime_config()
    thresholds = get_market_threshold(market_type)
    odd = float(candidate["odd_entrada"])
    ev_decimal = float(candidate["ev_decimal"])

    if odd < thresholds.odd_min or odd > thresholds.extended_max:
        return None, "odd_out_of_range", None
    if ev_decimal < thresholds.edge_min:
        return None, "edge_below_min", None

    max_ev_percent = float(runtime.rules.get("max_ev_percent", 20.0))
    if ev_decimal * 100 > max_ev_percent:
        return None, "ev_outlier_above_max", _rejected_candidate_payload(candidate, reject_reason="ev_outlier_above_max")

    flags = assess_risk_flags(candidate)
    confidence_score, reasons, cap_value = _confidence_score(candidate, flags)
    blocked_flags = safety_gate_flags(flags)
    if blocked_flags:
        return (
            None,
            "safety_gate_blocked",
            _rejected_candidate_payload(
                candidate,
                reject_reason="safety_gate_blocked",
                flags=flags,
                confidence_score=confidence_score,
                confidence_cap=cap_value,
                safety_gate_flags=blocked_flags,
            ),
        )

    critical_present = bool(get_critical_flags().intersection(flags))
    in_extended = odd > thresholds.standard_max

    ext_rules = runtime.rules.get("extended_range", {})
    if in_extended and ext_rules.get("enabled", True):
        if ev_decimal < thresholds.edge_premium_extended:
            return None, "extended_range_requires_premium_signal", _rejected_candidate_payload(candidate, reject_reason="extended_range_requires_premium_signal", flags=flags, confidence_score=confidence_score, confidence_cap=cap_value)
        if confidence_score < int(ext_rules.get("min_confidence", 5)):
            return None, "extended_range_requires_premium_signal", _rejected_candidate_payload(candidate, reject_reason="extended_range_requires_premium_signal", flags=flags, confidence_score=confidence_score, confidence_cap=cap_value)
        if ext_rules.get("require_no_critical_flags", True) and critical_present:
            return None, "extended_range_requires_premium_signal", _rejected_candidate_payload(candidate, reject_reason="extended_range_requires_premium_signal", flags=flags, confidence_score=confidence_score, confidence_cap=cap_value)
        if ext_rules.get("require_no_flags", True) and flags:
            return None, "extended_range_requires_premium_signal", _rejected_candidate_payload(candidate, reject_reason="extended_range_requires_premium_signal", flags=flags, confidence_score=confidence_score, confidence_cap=cap_value)

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
        return None, "low_confidence_or_critical_flag", _rejected_candidate_payload(candidate, reject_reason="low_confidence_or_critical_flag", flags=flags, confidence_score=confidence_score, confidence_cap=cap_value)

    fair_odd = candidate.get("odd_justa")
    fair_odd = round(float(fair_odd), 2) if fair_odd else None

    market_priority = get_market_priority()
    return {
        **candidate,
        "bet_id": _candidate_identity(candidate),
        "odd_justa": fair_odd,
        "ev_percent": round(ev_decimal * 100, 2),
        "pricing_signal_type": PRICING_SIGNAL_TYPE,
        "confidence_score": confidence_score,
        "confidence_score_type": CONFIDENCE_SCORE_TYPE,
        "confidence_score_scale": CONFIDENCE_SCORE_SCALE,
        "confidence_cap": cap_value,
        "stake_units": stake_units,
        "entry_reason": "|".join(reasons[:4]) if reasons else "SEM_MOTIVO",
        "risk_flags": "|".join(flags) if flags else "SEM_FLAG",
        "pick_safety_status": "safe",
        "candidate_stage": "eligible_pick",
        "decision_policy_status": "eligible",
        "decision_reject_reason": "",
        "safety_gate_reason": "",
        "market_priority": market_priority.get(market_type, 99),
        "strategy_config_name": runtime.name,
        "strategy_config_fingerprint": runtime.fingerprint,
    }, None, None


def evaluate_pick_candidate_with_meta(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    evaluated, reject_reason, _rejected_payload = evaluate_pick_candidate_with_details(candidate)
    return evaluated, reject_reason


def evaluate_pick_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    evaluated, _ = evaluate_pick_candidate_with_meta(candidate)
    return evaluated
