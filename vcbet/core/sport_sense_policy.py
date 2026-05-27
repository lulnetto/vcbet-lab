from __future__ import annotations

import unicodedata
from typing import Any

from vcbet.core.strategy_config import OddRange, RuntimeConfig


APPROVED = "approved"
PENALIZED = "penalized"
BLOCKED = "blocked"


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "nan", "none", "<na>", "null"}


def _fold(value: Any) -> str:
    if _is_missing(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().casefold().split())


def _num(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_num(pick: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = _num(pick.get(name))
        if value is not None:
            return value
    return None


def _section(config: RuntimeConfig | dict[str, Any], name: str) -> dict[str, Any]:
    value = getattr(config, name, None)
    if isinstance(value, dict):
        return value
    payload = getattr(config, "payload", config if isinstance(config, dict) else {})
    value = payload.get(name) if isinstance(payload, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def _enabled(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _fold(value) not in {"", "0", "false", "no", "nao", "disabled", "none", "null"}


def _market_type(pick: dict[str, Any]) -> str:
    return _fold(pick.get("market_type") or pick.get("market"))


def _selection_text(pick: dict[str, Any]) -> str:
    parts = [
        pick.get("selection"),
        pick.get("selection_name"),
        pick.get("selection_raw"),
        pick.get("market"),
        pick.get("market_raw"),
    ]
    return " ".join(_fold(part) for part in parts if not _is_missing(part))


def normalize_btts_side(value: Any) -> str:
    text = _fold(value)
    if not text:
        return "unknown"
    yes_aliases = {
        "yes",
        "sim",
        "btts yes",
        "ambas marcam sim",
        "ambos marcam sim",
        "ambas equipes marcam sim",
    }
    no_aliases = {
        "no",
        "nao",
        "btts no",
        "btts nao",
        "ambas marcam nao",
        "ambos marcam nao",
        "ambas equipes marcam nao",
    }
    if text in yes_aliases:
        return "yes"
    if text in no_aliases:
        return "no"
    if "btts" in text and "yes" in text:
        return "yes"
    if "btts" in text and (" no" in f" {text}" or "nao" in text):
        return "no"
    if "ambas" in text and "marcam" in text and "sim" in text:
        return "yes"
    if "ambas" in text and "marcam" in text and "nao" in text:
        return "no"
    return "unknown"


def _total_side(pick: dict[str, Any]) -> str:
    text = _fold(pick.get("side"))
    selection = _selection_text(pick)
    combined = " ".join(part for part in (text, selection) if part)
    if text in {"over", "mais", "acima"} or " over " in f" {combined} " or "mais de" in combined:
        return "over"
    if text in {"under", "menos", "abaixo"} or " under " in f" {combined} " or "menos de" in combined:
        return "under"
    return "unknown"


def _target_side(pick: dict[str, Any]) -> str | None:
    role = _fold(pick.get("target_team_role"))
    if role in {"home", "casa", "mandante"}:
        return "home"
    if role in {"away", "fora", "visitante"}:
        return "away"

    home = _fold(pick.get("home_team"))
    away = _fold(pick.get("away_team"))
    target = _fold(pick.get("target_team_name"))
    selection = _selection_text(pick)

    if target:
        if home and (target == home or target in home or home in target):
            return "home"
        if away and (target == away or target in away or away in target):
            return "away"
    if selection:
        if home and home in selection:
            return "home"
        if away and away in selection:
            return "away"
    return None


def _favorite_side_from_lower(home_value: float | None, away_value: float | None) -> str | None:
    if home_value is None or away_value is None:
        return None
    if abs(home_value - away_value) <= 1e-9:
        return "neutral"
    return "home" if home_value < away_value else "away"


def _favorite_side_from_higher(home_value: float | None, away_value: float | None) -> str | None:
    if home_value is None or away_value is None:
        return None
    if abs(home_value - away_value) <= 0.05:
        return "neutral"
    return "home" if home_value > away_value else "away"


def _role_for_target(target: str | None, favorite_side: str | None, source: str) -> tuple[str, str] | None:
    if target is None or favorite_side is None:
        return None
    if favorite_side == "neutral":
        return "neutral", source
    return ("favorite" if target == favorite_side else "underdog"), source


def infer_team_role(pick: dict[str, Any]) -> tuple[str, str]:
    target = _target_side(pick)

    market_favorite = _favorite_side_from_lower(
        _first_num(pick, "home_odd", "odd_home", "home_market_odd"),
        _first_num(pick, "away_odd", "odd_away", "away_market_odd"),
    )
    role = _role_for_target(target, market_favorite, "market_1x2")
    if role is not None:
        return role

    fair_favorite = _favorite_side_from_lower(
        _first_num(pick, "fair_home", "home_fair_odd", "odd_justa_home"),
        _first_num(pick, "fair_away", "away_fair_odd", "odd_justa_away"),
    )
    role = _role_for_target(target, fair_favorite, "model_fair")
    if role is not None:
        return role

    lambda_favorite = _favorite_side_from_higher(
        _first_num(pick, "home_lambda", "lambda_home", "lambda_home_adjusted", "lambda_home_base"),
        _first_num(pick, "away_lambda", "lambda_away", "lambda_away_adjusted", "lambda_away_base"),
    )
    role = _role_for_target(target, lambda_favorite, "lambda")
    if role is not None:
        return role

    return "unknown", "unknown"


def _range_contains(odd_range: OddRange | dict[str, Any], odd: float) -> bool:
    if isinstance(odd_range, OddRange):
        return odd_range.contains(odd)
    if isinstance(odd_range, dict):
        low = _num(odd_range.get("min"))
        high = _num(odd_range.get("max"))
        return low is not None and high is not None and low <= odd <= high
    return False


def _ranges(config: RuntimeConfig | dict[str, Any], field: str, market_type: str) -> tuple[Any, ...]:
    if field == "allowed_odd_ranges" and hasattr(config, "allowed_odd_ranges_for_market"):
        return tuple(config.allowed_odd_ranges_for_market(market_type))  # type: ignore[attr-defined]
    if field == "blocked_odd_ranges" and hasattr(config, "blocked_odd_ranges_for_market"):
        return tuple(config.blocked_odd_ranges_for_market(market_type))  # type: ignore[attr-defined]
    payload = getattr(config, "payload", config if isinstance(config, dict) else {})
    value = payload.get(field) if isinstance(payload, dict) else None
    return tuple(value) if isinstance(value, list) else ()


def _normalize_ev_decimal(value: Any) -> float | None:
    number = _num(value)
    if number is None:
        return None
    if abs(number) > 1.0:
        return number / 100.0
    return number


def configured_min_ev_decimal(config: RuntimeConfig | dict[str, Any], market_type: str) -> float | None:
    policy = _section(config, "ev_policy")
    min_by_market = policy.get("min_ev_by_market")
    if not isinstance(min_by_market, dict):
        return None
    return _normalize_ev_decimal(min_by_market.get(market_type))


def _pick_ev_decimal(pick: dict[str, Any]) -> float | None:
    if not _is_missing(pick.get("ev_decimal")):
        return _normalize_ev_decimal(pick.get("ev_decimal"))
    if not _is_missing(pick.get("ev_percent")):
        return _normalize_ev_decimal(pick.get("ev_percent"))
    return None


def should_ignore_global_mercado_time(config: RuntimeConfig | dict[str, Any]) -> bool:
    policy = _section(config, "sport_sense_policy")
    team_total_policy = policy.get("team_total_policy")
    if not isinstance(team_total_policy, dict):
        return False
    return _enabled(team_total_policy.get("block_global_mercado_time_flag"), default=False)


def _split_flags(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text or text.upper() == "SEM_FLAG":
        return []
    return [part.strip() for part in text.replace(",", "|").split("|") if part.strip() and part.strip().upper() != "SEM_FLAG"]


def strip_global_mercado_time_flag(pick: dict[str, Any], config: RuntimeConfig | dict[str, Any]) -> dict[str, Any]:
    if _market_type(pick) != "team_total" or not should_ignore_global_mercado_time(config):
        return pick
    flags = [flag for flag in _split_flags(pick.get("risk_flags")) if flag != "MERCADO_TIME"]
    pick["risk_flags"] = "|".join(flags) if flags else "SEM_FLAG"
    return pick


def _blocked(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    payload["sport_sense_status"] = BLOCKED
    payload["sport_sense_reason"] = reason
    payload.setdefault("stake_policy_applied", False)
    payload.setdefault("stake_policy_reason", "")
    original = _first_num(payload, "stake_units", "stake")
    if original is not None:
        payload.setdefault("original_stake", original)
        payload.setdefault("stake", original)
    return payload


def _cap_stake(current: float, cap: float | None, reason: str, reasons: list[str]) -> float:
    if cap is None:
        return current
    if current > cap:
        reasons.append(reason)
        return cap
    return current


def apply_stake_policy(pick: dict[str, Any], config: RuntimeConfig | dict[str, Any]) -> dict[str, Any]:
    policy = _section(config, "stake_policy")
    original = _first_num(pick, "stake_units", "stake")
    if not policy:
        pick["stake_policy_applied"] = False
        pick["stake_policy_reason"] = ""
        if original is not None:
            pick["original_stake"] = original
            pick["stake"] = original
        return pick

    if original is None:
        original = _num(policy.get("default_stake")) or 0.0
    default_stake = _num(policy.get("default_stake"))
    stake = default_stake if default_stake is not None else original
    reasons = ["DEFAULT_STAKE" if default_stake is not None else "EXISTING_STAKE"]

    market_type = _market_type(pick)
    full_stake = _num(policy.get("full_stake"))
    full_only_for = {
        _fold(item)
        for item in policy.get("full_stake_only_for", [])
        if not _is_missing(item)
    } if isinstance(policy.get("full_stake_only_for"), list) else set()

    if full_stake is not None and original >= full_stake:
        if not full_only_for or market_type in full_only_for:
            stake = max(stake, full_stake)
            reasons.append("FULL_STAKE_ALLOWED")
        else:
            reasons.append("FULL_STAKE_MARKET_NOT_ALLOWED")
    if full_stake is not None and full_only_for and market_type not in full_only_for and stake >= full_stake:
        fallback = default_stake if default_stake is not None else min(original, full_stake)
        stake = min(stake, fallback)

    reduced = policy.get("reduced_stake_for")
    if isinstance(reduced, dict):
        stake = _cap_stake(stake, _num(reduced.get(market_type)), "REDUCED_MARKET_CAP", reasons)

    odd = _first_num(pick, "odd_entrada", "odd", "price")
    if odd is not None and odd >= 2.50:
        stake = _cap_stake(stake, _num(policy.get("odds_above_2_50_max_stake")), "ODDS_ABOVE_2_50_CAP", reasons)

    stake = _cap_stake(stake, _num(policy.get("max_stake")), "MAX_STAKE_CAP", reasons)

    pick["stake_policy_applied"] = True
    pick["stake_policy_reason"] = "|".join(dict.fromkeys(reasons))
    pick["original_stake"] = float(original)
    pick["stake"] = float(stake)
    pick["stake_units"] = float(stake)
    return pick


def _apply_odd_policy(payload: dict[str, Any], config: RuntimeConfig | dict[str, Any]) -> str | None:
    odd = _first_num(payload, "odd_entrada", "odd", "price")
    if odd is None:
        return None
    market_type = _market_type(payload)
    blocked = _ranges(config, "blocked_odd_ranges", market_type)
    if any(_range_contains(odd_range, odd) for odd_range in blocked):
        return "ODD_IN_BLOCKED_RANGE"
    allowed = _ranges(config, "allowed_odd_ranges", market_type)
    if allowed and not any(_range_contains(odd_range, odd) for odd_range in allowed):
        return "ODD_OUTSIDE_ALLOWED_RANGES"
    return None


def _apply_btts_side_policy(payload: dict[str, Any], config: RuntimeConfig | dict[str, Any]) -> str | None:
    if _market_type(payload) != "btts":
        return None
    rules = _section(config, "side_rules").get("btts")
    if not isinstance(rules, dict):
        return None
    side = normalize_btts_side(payload.get("side") or payload.get("selection") or payload.get("selection_name") or payload.get("selection_raw"))
    if side == "unknown":
        return None

    blocked = {
        normalize_btts_side(item)
        for item in rules.get("blocked_sides", [])
        if not _is_missing(item)
    } if isinstance(rules.get("blocked_sides"), list) else set()
    if side in blocked:
        return "BTTS_SIDE_BLOCKED"

    if "allowed_sides" in rules:
        allowed = {
            normalize_btts_side(item)
            for item in rules.get("allowed_sides", [])
            if not _is_missing(item)
        } if isinstance(rules.get("allowed_sides"), list) else set()
        if side not in allowed:
            return "BTTS_SIDE_BLOCKED"
    return None


def _team_total_policy(config: RuntimeConfig | dict[str, Any]) -> dict[str, Any]:
    policy = _section(config, "sport_sense_policy")
    if not _enabled(policy.get("enabled"), default=bool(policy)):
        return {}
    team_policy = policy.get("team_total_policy")
    if not isinstance(team_policy, dict) or not _enabled(team_policy.get("enabled"), default=True):
        return {}
    return team_policy


def _line_eq(line: float, target: float) -> bool:
    return abs(line - target) <= 1e-9


def _apply_team_total_semantics(payload: dict[str, Any], config: RuntimeConfig | dict[str, Any]) -> tuple[str, str]:
    if _market_type(payload) != "team_total":
        return APPROVED, "APPROVED"
    policy = _team_total_policy(config)
    if not policy:
        return APPROVED, "APPROVED"

    role = payload.get("team_role") or "unknown"
    side = _total_side(payload)
    line = _first_num(payload, "line", "handicap")
    if role == "unknown":
        return APPROVED, "TEAM_ROLE_UNKNOWN"
    if side == "unknown":
        return APPROVED, "TEAM_TOTAL_SIDE_UNKNOWN"
    if line is None:
        return APPROVED, "TEAM_TOTAL_LINE_UNKNOWN"

    semantic_side = f"{role}_{side}" if role in {"favorite", "underdog"} else "unknown"
    payload["team_total_semantic_side"] = semantic_side

    underdog_over_allow = _num(policy.get("underdog_over_allow_lines_lte"))
    underdog_over_block = _num(policy.get("underdog_over_block_lines_gte"))
    favorite_under_allow = _num(policy.get("favorite_under_allow_lines_gte"))
    favorite_under_block = _num(policy.get("favorite_under_block_lines_lte"))
    underdog_over_allow = 0.5 if underdog_over_allow is None else underdog_over_allow
    underdog_over_block = 1.5 if underdog_over_block is None else underdog_over_block
    favorite_under_allow = 2.5 if favorite_under_allow is None else favorite_under_allow
    favorite_under_block = 1.5 if favorite_under_block is None else favorite_under_block

    if semantic_side == "underdog_over":
        if line <= underdog_over_allow:
            return APPROVED, "UNDERDOG_OVER_LOW_LINE_OK"
        if line >= underdog_over_block:
            return BLOCKED, "UNDERDOG_OVER_AGGRESSIVE_LINE"
        return PENALIZED, "UNDERDOG_OVER_INTERMEDIATE_LINE"

    if semantic_side == "favorite_under":
        if line >= favorite_under_allow:
            if _line_eq(line, 3.0) and _enabled(policy.get("favorite_under_prefer_push_lines"), default=False):
                return APPROVED, "FAVORITE_UNDER_PUSH_LINE_OK"
            return APPROVED, "FAVORITE_UNDER_HIGH_LINE_OK"
        if line <= favorite_under_block:
            return BLOCKED, "FAVORITE_UNDER_ANTI_FOOTBALL"
        return PENALIZED, "FAVORITE_UNDER_LOW_LINE"

    if semantic_side == "favorite_over":
        if line <= 2.5:
            return APPROVED, "FAVORITE_OVER_OK"
        return PENALIZED, "FAVORITE_OVER_HIGH_LINE"

    if semantic_side == "underdog_under":
        if line >= 1.5:
            return APPROVED, "UNDERDOG_UNDER_OK"
        return PENALIZED, "UNDERDOG_UNDER_LOW_LINE"

    return APPROVED, "TEAM_ROLE_UNKNOWN"


def apply_sport_sense_policy(pick: dict[str, Any], config: RuntimeConfig | dict[str, Any]) -> dict[str, Any]:
    payload = dict(pick)
    role, source = infer_team_role(payload)
    payload["team_role"] = role
    payload["team_role_source"] = source
    payload.setdefault("sport_sense_status", APPROVED)
    payload.setdefault("sport_sense_reason", "APPROVED")
    strip_global_mercado_time_flag(payload, config)

    odd_reason = _apply_odd_policy(payload, config)
    if odd_reason:
        return _blocked(payload, odd_reason)

    btts_reason = _apply_btts_side_policy(payload, config)
    if btts_reason:
        return _blocked(payload, btts_reason)

    min_ev = configured_min_ev_decimal(config, _market_type(payload))
    ev_decimal = _pick_ev_decimal(payload)
    if min_ev is not None and ev_decimal is not None and ev_decimal < min_ev:
        return _blocked(payload, "EV_BELOW_MARKET_MIN")

    status, reason = _apply_team_total_semantics(payload, config)
    payload["sport_sense_status"] = status
    payload["sport_sense_reason"] = reason
    if status == BLOCKED:
        return _blocked(payload, reason)

    return apply_stake_policy(payload, config)
