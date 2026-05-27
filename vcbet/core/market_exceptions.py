from __future__ import annotations

from typing import Any

from vcbet.core.sport_sense_policy import normalize_btts_side


EV_EXCEPTION_BTTS_YES_EXPERIMENTAL = "EV_EXCEPTION_BTTS_YES_EXPERIMENTAL"


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "nan", "none", "<na>", "null"}


def _num(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fold(value: Any) -> str:
    if _is_missing(value):
        return ""
    return " ".join(str(value).strip().casefold().split())


def _first(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if not _is_missing(value):
            return value
    return None


def _section(config: Any, name: str) -> dict[str, Any]:
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
    return _fold(value) not in {"", "0", "false", "no", "nao", "não", "disabled", "none", "null"}


def _ev_decimal(payload: dict[str, Any]) -> float | None:
    value = _num(payload.get("ev_decimal"))
    if value is None:
        value = _num(payload.get("ev_percent"))
        if value is not None and abs(value) > 1.0:
            value = value / 100.0
    return value


def _min_ev_decimal(config: Any, market_type: str) -> float | None:
    min_by_market = _section(config, "ev_policy").get("min_ev_by_market")
    if not isinstance(min_by_market, dict):
        return None
    value = _num(min_by_market.get(market_type))
    if value is not None and abs(value) > 1.0:
        value = value / 100.0
    return value


def _btts_yes_exception_config(config: Any) -> dict[str, Any]:
    btts = _section(config, "market_exceptions").get("btts")
    if not isinstance(btts, dict):
        return {}
    yes = btts.get("yes")
    return dict(yes) if isinstance(yes, dict) else {}


def _btts_side_rules_keep(side: str, config: Any) -> bool:
    btts = _section(config, "side_rules").get("btts")
    if not isinstance(btts, dict):
        return True
    blocked = {
        normalize_btts_side(item)
        for item in btts.get("blocked_sides", [])
        if not _is_missing(item)
    } if isinstance(btts.get("blocked_sides"), list) else set()
    if side in blocked:
        return False
    if "allowed_sides" not in btts:
        return True
    allowed = {
        normalize_btts_side(item)
        for item in btts.get("allowed_sides", [])
        if not _is_missing(item)
    } if isinstance(btts.get("allowed_sides"), list) else set()
    return side in allowed


def btts_yes_ev_exception_meta(
    payload: dict[str, Any],
    config: Any,
    *,
    min_ev_decimal: float | None = None,
) -> dict[str, Any] | None:
    if _fold(payload.get("market_type")) != "btts":
        return None
    side = normalize_btts_side(_first(payload, "side", "selection", "selection_name", "selection_raw"))
    if side != "yes":
        return None

    exception = _btts_yes_exception_config(config)
    if not exception or _enabled(exception.get("blocked"), default=False):
        return None
    if _enabled(exception.get("requires_sport_sense"), default=False) and not _btts_side_rules_keep(side, config):
        return None

    normal_min_ev = min_ev_decimal if min_ev_decimal is not None else _min_ev_decimal(config, "btts")
    ev_decimal = _ev_decimal(payload)
    floor = _num(exception.get("allow_negative_ev_floor"))
    if normal_min_ev is None or ev_decimal is None or floor is None:
        return None
    if ev_decimal >= normal_min_ev or ev_decimal < floor:
        return None

    odd = _num(_first(payload, "odd_entrada", "odd", "price"))
    min_odd = _num(exception.get("min_odd"))
    max_odd = _num(exception.get("max_odd"))
    if odd is None or min_odd is None or max_odd is None or odd < min_odd or odd > max_odd:
        return None

    stake_cap = _num(exception.get("stake_cap"))
    return {
        "reason": EV_EXCEPTION_BTTS_YES_EXPERIMENTAL,
        "stake_cap": stake_cap,
        "normal_min_ev": normal_min_ev,
        "ev_decimal": ev_decimal,
    }


def apply_market_exception_fields(payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    reason = str(meta.get("reason") or EV_EXCEPTION_BTTS_YES_EXPERIMENTAL)
    result["market_exception_applied"] = True
    result["market_exception_reason"] = reason
    stake_cap = _num(meta.get("stake_cap"))
    if stake_cap is not None:
        original = _num(_first(result, "original_stake", "stake_units", "stake"))
        if original is not None:
            result.setdefault("original_stake", original)
        for field in ("stake_units", "stake"):
            value = _num(result.get(field))
            if value is not None and value > stake_cap:
                result[field] = stake_cap
        if _num(result.get("stake_units")) is None:
            result["stake_units"] = stake_cap
        if _num(result.get("stake")) is None:
            result["stake"] = stake_cap
    result["stake_policy_applied"] = True
    existing_reason = str(result.get("stake_policy_reason") or "").strip()
    reasons = [item for item in existing_reason.split("|") if item]
    reasons.append(reason)
    result["stake_policy_reason"] = "|".join(dict.fromkeys(reasons))
    return result
