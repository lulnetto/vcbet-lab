from __future__ import annotations

from statistics import median
from typing import Any, Mapping

from vcbet.core.pricing_engine import calculate_lambdas


XG_ONLY_PRICING_VARIANT = "xg_only"
XG_RESIDUAL_ADJUSTED_PRICING_VARIANT = "xg_residual_adjusted_v1"

DEFAULT_RESIDUAL_MARKETS = [
    "draw_no_bet",
    "asian_handicap",
    "asian_total",
    "total_goals",
    "team_total",
    "btts",
]

DEFAULT_XG_RESIDUAL_ADJUSTMENT = {
    "enabled": False,
    "weight": 0.25,
    "max_residual_abs": 0.35,
    "max_lambda_adjustment_pct": 0.07,
    "shrink_prior_games": 12,
    "min_games": 8,
    "markets": DEFAULT_RESIDUAL_MARKETS,
}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        unequal_to_self = value != value
        if isinstance(unequal_to_self, bool) and unequal_to_self:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if text in {"", "nan", "none", "<na>"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_get(row: Mapping[str, Any] | Any, name: str) -> Any:
    if hasattr(row, "get"):
        return row.get(name)
    try:
        return row[name]
    except Exception:
        return None


def _row_float(row: Mapping[str, Any] | Any, name: str) -> float | None:
    return _float_or_none(_row_get(row, name))


def _row_float_with_fallback(row: Mapping[str, Any] | Any, primary: str, fallback: str) -> float:
    primary_value = _row_float(row, primary)
    if primary_value is not None:
        return primary_value
    fallback_value = _row_float(row, fallback)
    if fallback_value is not None:
        return fallback_value
    return 0.01


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def cap_pct(value: float, *, base: float, max_pct: float) -> float:
    if max_pct < 0:
        max_pct = 0.0
    base_value = float(base)
    if base_value <= 0:
        return max(float(value), 0.01)
    lower = base_value * (1.0 - max_pct)
    upper = base_value * (1.0 + max_pct)
    return clamp(float(value), lower, upper)


def normalized_xg_residual_adjustment_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = dict(DEFAULT_XG_RESIDUAL_ADJUSTMENT)
    if isinstance(config, Mapping):
        normalized.update(dict(config))
    normalized["enabled"] = bool(normalized.get("enabled", False))
    normalized["weight"] = float(normalized.get("weight", DEFAULT_XG_RESIDUAL_ADJUSTMENT["weight"]))
    normalized["max_residual_abs"] = abs(float(normalized.get("max_residual_abs", DEFAULT_XG_RESIDUAL_ADJUSTMENT["max_residual_abs"])))
    normalized["max_lambda_adjustment_pct"] = abs(float(normalized.get("max_lambda_adjustment_pct", DEFAULT_XG_RESIDUAL_ADJUSTMENT["max_lambda_adjustment_pct"])))
    normalized["shrink_prior_games"] = max(0.0, float(normalized.get("shrink_prior_games", DEFAULT_XG_RESIDUAL_ADJUSTMENT["shrink_prior_games"])))
    normalized["min_games"] = max(0.0, float(normalized.get("min_games", DEFAULT_XG_RESIDUAL_ADJUSTMENT["min_games"])))
    markets = normalized.get("markets", DEFAULT_RESIDUAL_MARKETS)
    if not isinstance(markets, list):
        markets = list(DEFAULT_RESIDUAL_MARKETS)
    normalized["markets"] = [str(market) for market in markets]
    return normalized


def pricing_variant_from_payload(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return XG_ONLY_PRICING_VARIANT
    variant = str(payload.get("pricing_variant") or XG_ONLY_PRICING_VARIANT).strip()
    return variant or XG_ONLY_PRICING_VARIANT


def xg_residual_adjustment_from_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    config = payload.get("xg_residual_adjustment") if isinstance(payload, Mapping) else None
    return normalized_xg_residual_adjustment_config(config if isinstance(config, Mapping) else None)


def quality_xg_residual_adjustment_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    config = xg_residual_adjustment_from_payload(payload)
    if not config["enabled"]:
        return {"enabled": False}
    return {
        "enabled": True,
        "weight": config["weight"],
        "max_residual_abs": config["max_residual_abs"],
        "max_lambda_adjustment_pct": config["max_lambda_adjustment_pct"],
        "shrink_prior_games": config["shrink_prior_games"],
        "min_games": config["min_games"],
        "markets": config["markets"],
    }


def estimate_games_from_xg(row: Mapping[str, Any] | Any) -> float | None:
    estimates: list[float] = []
    xg = _row_float(row, "xg")
    xga = _row_float(row, "xga")
    xg_raw_total = _row_float(row, "xg_raw_total")
    xga_raw_total = _row_float(row, "xga_raw_total")

    if xg is not None and xg > 0 and xg_raw_total is not None and xg_raw_total >= 0:
        estimates.append(xg_raw_total / xg)
    if xga is not None and xga > 0 and xga_raw_total is not None and xga_raw_total >= 0:
        estimates.append(xga_raw_total / xga)
    if not estimates:
        return None
    return float(median(estimates))


def calculate_team_residual_adjustment(
    row: Mapping[str, Any] | Any,
    adjustment_config: Mapping[str, Any] | None,
    *,
    attack_base: float | None = None,
    defense_base: float | None = None,
) -> dict[str, Any]:
    config = normalized_xg_residual_adjustment_config(adjustment_config)
    xg = _row_float(row, "xg")
    xga = _row_float(row, "xga")
    goals_for = _row_float(row, "goals_for_per_match")
    goals_against = _row_float(row, "goals_against_per_match")

    attack_base_value = float(attack_base if attack_base is not None else (xg if xg is not None else 0.01))
    defense_base_value = float(defense_base if defense_base is not None else (xga if xga is not None else 0.01))

    attack_residual = None if goals_for is None or xg is None else goals_for - xg
    defense_residual = None if goals_against is None or xga is None else goals_against - xga
    max_residual_abs = config["max_residual_abs"]
    attack_residual_clamped = (
        None if attack_residual is None else clamp(attack_residual, -max_residual_abs, max_residual_abs)
    )
    defense_residual_clamped = (
        None if defense_residual is None else clamp(defense_residual, -max_residual_abs, max_residual_abs)
    )

    games_estimate = estimate_games_from_xg(row)
    sample_ok = games_estimate is not None and games_estimate >= config["min_games"]
    low_sample = games_estimate is not None and games_estimate < config["min_games"]
    missing_sample = games_estimate is None
    if sample_ok:
        shrink = games_estimate / (games_estimate + config["shrink_prior_games"])
    else:
        shrink = 0.0

    apply_adjustment = bool(config["enabled"] and sample_ok)
    attack_delta = (
        config["weight"] * shrink * attack_residual_clamped
        if apply_adjustment and attack_residual_clamped is not None
        else 0.0
    )
    defense_delta = (
        config["weight"] * shrink * defense_residual_clamped
        if apply_adjustment and defense_residual_clamped is not None
        else 0.0
    )

    adjusted_attack_xg = cap_pct(
        attack_base_value + attack_delta,
        base=attack_base_value,
        max_pct=config["max_lambda_adjustment_pct"],
    )
    adjusted_defense_xga = cap_pct(
        defense_base_value + defense_delta,
        base=defense_base_value,
        max_pct=config["max_lambda_adjustment_pct"],
    )
    adjusted_attack_xg = max(adjusted_attack_xg, 0.01)
    adjusted_defense_xga = max(adjusted_defense_xga, 0.01)

    return {
        "goals_for_per_match": goals_for,
        "goals_against_per_match": goals_against,
        "attack_residual": attack_residual,
        "defense_residual": defense_residual,
        "attack_residual_clamped": attack_residual_clamped,
        "defense_residual_clamped": defense_residual_clamped,
        "games_estimate": games_estimate,
        "residual_shrink": shrink,
        "residual_low_sample": bool(low_sample),
        "residual_missing_sample": bool(missing_sample),
        "adjusted_attack_xg": adjusted_attack_xg,
        "adjusted_defense_xga": adjusted_defense_xga,
        "residual_adjustment_applied": bool(
            apply_adjustment
            and (
                abs(adjusted_attack_xg - attack_base_value) > 1e-12
                or abs(adjusted_defense_xga - defense_base_value) > 1e-12
            )
        ),
    }


def _lambda_adjustment_pct(base: float, adjusted: float) -> float:
    if base <= 0:
        return 0.0
    return (adjusted - base) / base


def _residual_values(*team_adjustments: dict[str, Any], field: str) -> list[float]:
    values: list[float] = []
    for adjustment in team_adjustments:
        value = _float_or_none(adjustment.get(field))
        if value is not None:
            values.append(value)
    return values


def build_xg_observational_flags(
    *,
    home_adjustment: dict[str, Any],
    away_adjustment: dict[str, Any],
    residual_adjustment_enabled: bool,
    lambda_home_adjustment_pct: float,
    lambda_away_adjustment_pct: float,
) -> list[str]:
    flags: set[str] = set()
    attack_residuals = _residual_values(home_adjustment, away_adjustment, field="attack_residual")
    defense_residuals = _residual_values(home_adjustment, away_adjustment, field="defense_residual")
    all_residuals = attack_residuals + defense_residuals
    tolerance = 0.05

    if all_residuals and all(abs(value) <= 0.10 for value in all_residuals):
        flags.add("GD_XG_ALIGNED")
    if any(value > tolerance for value in attack_residuals):
        flags.add("GD_XG_ATTACK_OVERPERFORMANCE")
    if any(value < -tolerance for value in attack_residuals):
        flags.add("GD_XG_ATTACK_UNDERPERFORMANCE")
    if any(value < -tolerance for value in defense_residuals):
        flags.add("GD_XG_DEFENSE_OVERPERFORMANCE")
    if any(value > tolerance for value in defense_residuals):
        flags.add("GD_XG_DEFENSE_UNDERPERFORMANCE")
    if residual_adjustment_enabled and (
        abs(lambda_home_adjustment_pct) > 1e-12 or abs(lambda_away_adjustment_pct) > 1e-12
    ):
        flags.add("GD_XG_RESIDUAL_ADJUSTED")
    if residual_adjustment_enabled and (
        home_adjustment.get("residual_low_sample")
        or away_adjustment.get("residual_low_sample")
        or home_adjustment.get("residual_missing_sample")
        or away_adjustment.get("residual_missing_sample")
    ):
        flags.add("GD_XG_RESIDUAL_NOT_APPLIED_LOW_SAMPLE")
    return sorted(flags)


def build_xg_residual_pricing_setup(
    *,
    home_xg_row: Mapping[str, Any] | Any,
    away_xg_row: Mapping[str, Any] | Any,
    market_type: str,
    runtime_config: Any,
) -> dict[str, Any]:
    payload = getattr(runtime_config, "payload", {}) if runtime_config is not None else {}
    pricing_variant = pricing_variant_from_payload(payload)
    adjustment_config = xg_residual_adjustment_from_payload(payload)
    residual_adjustment_enabled = bool(
        pricing_variant == XG_RESIDUAL_ADJUSTED_PRICING_VARIANT
        and adjustment_config["enabled"]
        and str(market_type) in set(adjustment_config["markets"])
    )
    effective_adjustment_config = dict(adjustment_config)
    effective_adjustment_config["enabled"] = residual_adjustment_enabled

    home_attack_base = _row_float_with_fallback(home_xg_row, "xg_home", "xg")
    home_defense_base = _row_float_with_fallback(home_xg_row, "xga_home", "xga")
    away_attack_base = _row_float_with_fallback(away_xg_row, "xg_away", "xg")
    away_defense_base = _row_float_with_fallback(away_xg_row, "xga_away", "xga")

    base_lambdas = calculate_lambdas(
        home_attack_base,
        home_defense_base,
        away_attack_base,
        away_defense_base,
    )
    home_adjustment = calculate_team_residual_adjustment(
        home_xg_row,
        effective_adjustment_config,
        attack_base=home_attack_base,
        defense_base=home_defense_base,
    )
    away_adjustment = calculate_team_residual_adjustment(
        away_xg_row,
        effective_adjustment_config,
        attack_base=away_attack_base,
        defense_base=away_defense_base,
    )
    adjusted_lambdas = calculate_lambdas(
        home_adjustment["adjusted_attack_xg"],
        home_adjustment["adjusted_defense_xga"],
        away_adjustment["adjusted_attack_xg"],
        away_adjustment["adjusted_defense_xga"],
    )
    lambda_home_adjustment_pct = _lambda_adjustment_pct(
        base_lambdas["lambda_home"], adjusted_lambdas["lambda_home"]
    )
    lambda_away_adjustment_pct = _lambda_adjustment_pct(
        base_lambdas["lambda_away"], adjusted_lambdas["lambda_away"]
    )
    observational_flags = build_xg_observational_flags(
        home_adjustment=home_adjustment,
        away_adjustment=away_adjustment,
        residual_adjustment_enabled=residual_adjustment_enabled,
        lambda_home_adjustment_pct=lambda_home_adjustment_pct,
        lambda_away_adjustment_pct=lambda_away_adjustment_pct,
    )

    diagnostics = {
        "pricing_variant": pricing_variant,
        "xg_residual_adjustment_enabled": residual_adjustment_enabled,
        "home_xg_base": home_attack_base,
        "away_xg_base": away_attack_base,
        "home_xga_base": home_defense_base,
        "away_xga_base": away_defense_base,
        "home_goals_for_per_match": home_adjustment["goals_for_per_match"],
        "away_goals_for_per_match": away_adjustment["goals_for_per_match"],
        "home_goals_against_per_match": home_adjustment["goals_against_per_match"],
        "away_goals_against_per_match": away_adjustment["goals_against_per_match"],
        "home_attack_residual": home_adjustment["attack_residual"],
        "away_attack_residual": away_adjustment["attack_residual"],
        "home_defense_residual": home_adjustment["defense_residual"],
        "away_defense_residual": away_adjustment["defense_residual"],
        "home_attack_residual_clamped": home_adjustment["attack_residual_clamped"],
        "away_attack_residual_clamped": away_adjustment["attack_residual_clamped"],
        "home_defense_residual_clamped": home_adjustment["defense_residual_clamped"],
        "away_defense_residual_clamped": away_adjustment["defense_residual_clamped"],
        "home_games_estimate": home_adjustment["games_estimate"],
        "away_games_estimate": away_adjustment["games_estimate"],
        "home_residual_shrink": home_adjustment["residual_shrink"],
        "away_residual_shrink": away_adjustment["residual_shrink"],
        "home_adjusted_attack_xg": home_adjustment["adjusted_attack_xg"],
        "away_adjusted_attack_xg": away_adjustment["adjusted_attack_xg"],
        "home_adjusted_defense_xga": home_adjustment["adjusted_defense_xga"],
        "away_adjusted_defense_xga": away_adjustment["adjusted_defense_xga"],
        "lambda_home_base": base_lambdas["lambda_home"],
        "lambda_away_base": base_lambdas["lambda_away"],
        "lambda_home_adjusted": adjusted_lambdas["lambda_home"],
        "lambda_away_adjusted": adjusted_lambdas["lambda_away"],
        "lambda_home_adjustment_pct": lambda_home_adjustment_pct,
        "lambda_away_adjustment_pct": lambda_away_adjustment_pct,
        "xg_observational_flags": "|".join(observational_flags) if observational_flags else "",
    }
    official_lambdas = adjusted_lambdas if residual_adjustment_enabled else base_lambdas
    return {
        "base_lambda_bundle": base_lambdas,
        "adjusted_lambda_bundle": adjusted_lambdas,
        "official_lambda_bundle": official_lambdas,
        "diagnostics": diagnostics,
    }
