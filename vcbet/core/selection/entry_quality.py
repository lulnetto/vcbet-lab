from __future__ import annotations

from typing import Any


ENTRY_QUALITY_FIELDS = (
    "entry_quality_score",
    "entry_quality_tier",
    "entry_quality_reasons",
    "entry_quality_market_component",
    "entry_quality_line_protection_component",
    "entry_quality_odds_component",
    "entry_quality_data_component",
    "entry_quality_risk_component",
    "entry_quality_ev_component",
)


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


def _split_flags(*values: Any) -> set[str]:
    flags: set[str] = set()
    for value in values:
        raw = _text(value)
        if not raw:
            continue
        for chunk in raw.replace(",", "|").split("|"):
            flag = chunk.strip().upper()
            if flag and flag != "SEM_FLAG":
                flags.add(flag)
    return flags


def _line_close(line: float | None, target: float) -> bool:
    return line is not None and abs(line - target) < 1e-9


def _ev_component(ev_percent: float | None) -> tuple[int, str]:
    ev = 0.0 if ev_percent is None else ev_percent
    if ev >= 18.0:
        return 25, "ev_ge_18"
    if ev >= 12.0:
        return 20, "ev_12_18"
    if ev >= 8.0:
        return 14, "ev_8_12"
    if ev >= 5.0:
        return 8, "ev_5_8"
    return 3, "ev_lt_5"


def _is_total_central(line: float | None) -> bool:
    return line is not None and 2.0 <= line <= 3.0


def _market_component(candidate: dict[str, Any], flags: set[str]) -> tuple[int, list[str]]:
    market_type = _clean(candidate.get("market_type"))
    line = _num(candidate.get("line"))
    reasons: list[str] = []

    if market_type == "draw_no_bet":
        component = 18
        reasons.append("market_dnb")
    elif market_type == "asian_handicap":
        if any(_line_close(line, target) for target in {0.5, 0.25, 0.0, -0.25, -0.5}):
            component = 18
            reasons.append("market_asian_handicap_protected")
        else:
            component = 14
            reasons.append("market_asian_handicap")
    elif market_type == "asian_total":
        component = 18 if _is_total_central(line) else 13
        reasons.append("market_asian_total_central" if _is_total_central(line) else "market_asian_total")
    elif market_type == "total_goals":
        component = 15 if _is_total_central(line) else 12
        reasons.append("market_total_goals_central" if _is_total_central(line) else "market_total_goals")
    elif market_type == "team_total":
        component = 12
        reasons.append("market_team_total")
    elif market_type == "btts":
        component = 10
        reasons.append("market_btts")
    else:
        component = 8
        reasons.append("market_other")

    if "LINHA_EXTREMA" in flags:
        component = max(0, component - 3)
        reasons.append("market_penalty_extreme_line")
    if "ODD_ALTA_VARIANCIA" in flags:
        component = max(0, component - 2)
        reasons.append("market_penalty_high_variance_odd")

    return component, reasons


def _asian_handicap_line_component(line: float | None) -> tuple[int, str]:
    if _line_close(line, 0.5):
        return 15, "line_ah_plus_0_5"
    if _line_close(line, 0.25):
        return 13, "line_ah_plus_0_25"
    if _line_close(line, 0.0):
        return 10, "line_ah_0"
    if _line_close(line, -0.25):
        return 7, "line_ah_minus_0_25"
    if _line_close(line, -0.5):
        return 5, "line_ah_minus_0_5"
    return 4, "line_ah_other"


def _total_line_component(side: str, line: float | None) -> tuple[int, str]:
    if line is None:
        return 5, "line_total_missing"
    if side == "over":
        if line <= 2.0:
            return 14, "line_total_over_2_0_or_lower"
        if line <= 2.25:
            return 12, "line_total_over_2_25"
        if line <= 2.5:
            return 10, "line_total_over_2_5"
        if line <= 2.75:
            return 7, "line_total_over_2_75"
        return 5, "line_total_over_3_0_or_higher"
    if side == "under":
        if line >= 3.0:
            return 14, "line_total_under_3_0_or_higher"
        if line >= 2.75:
            return 12, "line_total_under_2_75"
        if line >= 2.5:
            return 10, "line_total_under_2_5"
        if line >= 2.25:
            return 7, "line_total_under_2_25"
        return 5, "line_total_under_2_0_or_lower"
    return 5, "line_total_unknown_side"


def _line_protection_component(candidate: dict[str, Any]) -> tuple[int, str]:
    market_type = _clean(candidate.get("market_type"))
    side = _clean(candidate.get("side"))
    line = _num(candidate.get("line"))

    if market_type == "draw_no_bet":
        return 10, "line_dnb"
    if market_type == "asian_handicap":
        return _asian_handicap_line_component(line)
    if market_type in {"asian_total", "total_goals"}:
        return _total_line_component(side, line)
    if market_type == "team_total":
        return _total_line_component(side, line)
    return 4, "line_no_protection_model"


def _odds_component(candidate: dict[str, Any]) -> tuple[int, str]:
    odd = _num(candidate.get("odd_entrada"))
    if odd is None:
        odd = _num(candidate.get("odd"))
    if odd is None:
        return 0, "odds_missing"
    if 1.70 <= odd <= 2.20:
        return 15, "odds_1_70_2_20"
    if 2.20 < odd <= 2.60:
        return 11, "odds_2_20_2_60"
    if 2.60 < odd <= 2.90:
        return 7, "odds_2_60_2_90"
    if odd > 2.90:
        return 3, "odds_above_2_90"
    if odd < 1.65:
        return 4, "odds_below_1_65"
    return 8, "odds_1_65_1_70"


def _data_component(candidate: dict[str, Any], flags: set[str]) -> tuple[int, list[str]]:
    component = 0
    reasons: list[str] = []

    if "FOTMOB_GLOBAL_XG" in flags:
        reasons.append("data_fotmob_global_xg_info_only")
    if "GD_XG_RESIDUAL_ADJUSTED" in flags:
        component += 5
        reasons.append("data_gd_xg_residual_adjusted")
    if "GD_XG_RESIDUAL_NOT_APPLIED_LOW_SAMPLE" in flags:
        component -= 6
        reasons.append("data_low_sample_residual_not_applied")

    home_status = _text(candidate.get("match_status_home"))
    away_status = _text(candidate.get("match_status_away"))
    reliable_statuses = {"auto_exact", "MATCH_REGISTRY_APPROVED"}
    bad_match_flags = {"MATCH_FUZZY", "MATCH_DUVIDOSO", "MATCH_REGISTRY_PENDING", "MATCH_UNRESOLVED"}
    if "MATCH_FUZZY" in flags:
        component -= 20
        reasons.append("data_match_fuzzy")
    elif (home_status in reliable_statuses and away_status in reliable_statuses) or not flags.intersection(bad_match_flags):
        component += 5
        reasons.append("data_match_registry_or_no_fuzzy")

    return component, reasons


def _risk_component(flags: set[str]) -> tuple[int, list[str]]:
    penalties = {
        "LIGA_VOLATIL": 4,
        "ODD_ALTA_VARIANCIA": 6,
        "LINHA_EXTREMA": 7,
        "MERCADO_TIME": 3,
        "CORRELACAO_JOGO": 3,
        "DRAW_SENSITIVE_LINE": 2,
    }
    component = 0
    reasons: list[str] = []
    for flag, penalty in penalties.items():
        if flag in flags:
            component -= penalty
            reasons.append(f"risk_{flag.lower()}_minus_{penalty}")
    return component, reasons


def _tier(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def compute_entry_quality(candidate: dict[str, Any]) -> dict[str, Any]:
    flags = _split_flags(candidate.get("risk_flags"), candidate.get("xg_observational_flags"))
    reasons: list[str] = []

    ev_component, ev_reason = _ev_component(_num(candidate.get("ev_percent")))
    reasons.append(ev_reason)

    market_component, market_reasons = _market_component(candidate, flags)
    reasons.extend(market_reasons)

    line_component, line_reason = _line_protection_component(candidate)
    reasons.append(line_reason)

    odds_component, odds_reason = _odds_component(candidate)
    reasons.append(odds_reason)

    data_component, data_reasons = _data_component(candidate, flags)
    reasons.extend(data_reasons)

    risk_component, risk_reasons = _risk_component(flags)
    reasons.extend(risk_reasons)

    raw_score = ev_component + market_component + line_component + odds_component + data_component + risk_component
    score = max(0, min(100, int(round(raw_score))))

    return {
        "entry_quality_score": score,
        "entry_quality_tier": _tier(score),
        "entry_quality_reasons": "|".join(reasons),
        "entry_quality_market_component": market_component,
        "entry_quality_line_protection_component": line_component,
        "entry_quality_odds_component": odds_component,
        "entry_quality_data_component": data_component,
        "entry_quality_risk_component": risk_component,
        "entry_quality_ev_component": ev_component,
    }


def annotate_entry_quality(candidate: dict[str, Any]) -> None:
    candidate.update(compute_entry_quality(candidate))
