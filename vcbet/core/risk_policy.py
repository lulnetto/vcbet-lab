from __future__ import annotations

from typing import Any

from vcbet.core.config_ligas import liga_eh_caotica
from vcbet.core.market_thresholds import get_market_threshold
from vcbet.core.strategy_config import get_runtime_config


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


def assess_risk_flags(candidate: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    market_type = candidate["market_type"]
    line = candidate.get("line")
    odd = float(candidate["odd_entrada"])
    mu_total = float(candidate["mu_total"])
    thresholds = get_market_threshold(market_type)

    home_status = candidate.get("match_status_home")
    away_status = candidate.get("match_status_away")
    reliable_statuses = {"auto_exact", "manual_approved", "MATCH_REGISTRY_APPROVED", "auto_fuzzy_high"}
    if home_status not in reliable_statuses or away_status not in reliable_statuses:
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


def safety_gate_flags(flags: list[str]) -> list[str]:
    runtime = get_runtime_config()
    gate_cfg = runtime.rules.get("safety_gates", {})
    if not gate_cfg.get("enabled", True):
        return []
    blocked = set(gate_cfg.get("block_flags", ["MATCH_FUZZY", "MATCH_DUVIDOSO", "DADO_INCOMPLETO_LIGA"]))
    return sorted(blocked.intersection(flags))
