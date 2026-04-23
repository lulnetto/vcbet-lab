from __future__ import annotations

from hashlib import md5
from typing import Any


CHAOTIC_LEAGUES = {"Championship", "Serie B", "Ligue 2", "Segunda División"}
PRIMARY_MARKETS = {"total_goals", "asian_total"}
ALLOWED_MARKETS = {"total_goals", "team_total", "btts", "asian_total", "asian_handicap"}
MARKET_PRIORITY = {
    "total_goals": 1,
    "asian_total": 2,
    "asian_handicap": 3,
    "btts": 4,
    "team_total": 5,
}

MARKET_LIMITS = {
    "total_goals": {"odd_min": 1.65, "standard_max": 2.60, "extended_max": 3.20, "edge_min": 0.06},
    "team_total": {"odd_min": 1.70, "standard_max": 2.60, "extended_max": 3.00, "edge_min": 0.07},
    "btts": {"odd_min": 1.70, "standard_max": 2.40, "extended_max": 2.80, "edge_min": 0.07},
    "asian_total": {"odd_min": 1.70, "standard_max": 2.60, "extended_max": 3.00, "edge_min": 0.06},
    "asian_handicap": {"odd_min": 1.70, "standard_max": 2.60, "extended_max": 3.00, "edge_min": 0.07},
}

CRITICAL_FLAGS = {"MATCH_DUVIDOSO", "DADO_INCOMPLETO_LIGA"}


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

    if candidate.get("match_status_home") not in {"auto_exact", "manual_approved"} or candidate.get("match_status_away") not in {"auto_exact", "manual_approved"}:
        if candidate.get("match_status_home") not in {"auto_fuzzy_high", "auto_exact", "manual_approved"} or candidate.get("match_status_away") not in {"auto_fuzzy_high", "auto_exact", "manual_approved"}:
            flags.append("MATCH_DUVIDOSO")

    if candidate.get("xg_fallback_home") or candidate.get("xg_fallback_away"):
        flags.append("FALLBACK_XG_GLOBAL")
        if market_type in {"team_total", "asian_handicap"}:
            flags.append("DADO_INCOMPLETO_LIGA")

    if candidate["league"] in CHAOTIC_LEAGUES:
        flags.append("LIGA_VOLATIL")

    if market_type == "team_total":
        flags.append("MERCADO_TIME")

    if _line_extreme(market_type, line):
        flags.append("LINHA_EXTREMA")

    if odd > MARKET_LIMITS[market_type]["standard_max"]:
        flags.append("ODD_ALTA_VARIANCIA")

    if market_type == "asian_handicap" and line is not None:
        if abs(float(line)) in {0.0, 0.25}:
            flags.append("DRAW_SENSITIVE_LINE")
        if abs(float(line)) >= 1.0:
            flags.append("HEAVY_FAVORITE_LINE")
            flags.append("POISSON_MARGIN_RISK")

    if mu_total <= 2.1:
        flags.append("LOW_SCORE_MATCH")
    if mu_total >= 3.9:
        flags.append("HIGH_TOTAL_MATCH")

    return sorted(set(flags))


def _confidence_score(candidate: dict[str, Any], flags: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    ev_decimal = float(candidate["ev_decimal"])
    market_type = candidate["market_type"]

    edge_min = MARKET_LIMITS[market_type]["edge_min"]
    if ev_decimal >= 0.10:
        score += 2
        reasons.append("EDGE_FORTE")
    elif ev_decimal >= edge_min:
        score += 1
        reasons.append("EDGE_MODERADO")

    if market_type in PRIMARY_MARKETS:
        score += 1
        reasons.append("MERCADO_PRINCIPAL")

    if "DADO_INCOMPLETO_LIGA" not in flags:
        score += 1
        reasons.append("DADO_COMPLETO")

    if candidate.get("match_status_home") in {"auto_exact", "manual_approved"} and candidate.get("match_status_away") in {"auto_exact", "manual_approved"}:
        score += 1
        reasons.append("MATCH_CONFIAVEL")

    if candidate["league"] not in CHAOTIC_LEAGUES:
        score += 1
        reasons.append("LIGA_ESTAVEL")

    penalties = {
        "MERCADO_TIME": 1,
        "LIGA_VOLATIL": 1,
        "LINHA_EXTREMA": 1,
        "DRAW_SENSITIVE_LINE": 1,
        "LOW_SCORE_MATCH": 1,
        "HIGH_TOTAL_MATCH": 1,
        "POISSON_MARGIN_RISK": 1,
        "ODD_ALTA_VARIANCIA": 1,
        "CORRELACAO_JOGO": 1,
        "MATCH_DUVIDOSO": 2,
        "DADO_INCOMPLETO_LIGA": 2,
    }
    for flag in flags:
        score -= penalties.get(flag, 0)

    score = max(0, min(5, score))
    return score, reasons


def evaluate_pick_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    market_type = candidate["market_type"]
    if market_type not in ALLOWED_MARKETS:
        return None

    limits = MARKET_LIMITS[market_type]
    odd = float(candidate["odd_entrada"])
    ev_decimal = float(candidate["ev_decimal"])

    if odd < limits["odd_min"] or odd > limits["extended_max"]:
        return None
    if ev_decimal < limits["edge_min"]:
        return None

    flags = _base_risk_flags(candidate)
    confidence_score, reasons = _confidence_score(candidate, flags)

    critical_present = bool(CRITICAL_FLAGS.intersection(flags))
    in_extended = odd > limits["standard_max"]
    if in_extended and (ev_decimal < 0.10 or confidence_score < 4 or critical_present):
        return None

    if critical_present or confidence_score < 3:
        stake_units = 0.0
    elif confidence_score >= 4:
        stake_units = 1.0
    else:
        stake_units = 0.5

    if stake_units <= 0:
        return None

    fair_odd = candidate.get("odd_justa")
    fair_odd = round(float(fair_odd), 2) if fair_odd else None

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
        "stake_units": stake_units,
        "entry_reason": "|".join(reasons[:4]) if reasons else "SEM_MOTIVO",
        "risk_flags": "|".join(flags) if flags else "SEM_FLAG",
        "market_priority": MARKET_PRIORITY.get(market_type, 99),
    }
