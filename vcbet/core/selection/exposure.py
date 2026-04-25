from __future__ import annotations

from typing import Any

from vcbet.core.selection import market_family


def _exposure_rejection(
    candidate: dict[str, Any],
    selected_count_by_scope: dict[tuple[str, str], int],
    selected_stake_by_scope: dict[tuple[str, str], float],
    portfolio_rules: dict[str, Any],
) -> tuple[str, str, float] | None:
    stake = float(candidate.get("stake_units") or 0.0)
    league = str(candidate.get("league") or "unknown")
    family = str(candidate.get("market_family") or market_family(candidate))

    checks = [
        ("league", league, int(portfolio_rules.get("max_picks_per_league", 999)), float(portfolio_rules.get("max_stake_per_league", 999.0))),
        ("market_family", family, int(portfolio_rules.get("max_picks_per_market_family", 999)), float(portfolio_rules.get("max_stake_per_market_family", 999.0))),
    ]
    for scope_name, scope_value, max_count, max_stake in checks:
        key = (scope_name, scope_value)
        next_count = selected_count_by_scope.get(key, 0) + 1
        next_stake = selected_stake_by_scope.get(key, 0.0) + stake
        if next_count > max_count:
            return f"{scope_name.upper()}_PICK_LIMIT", f"{scope_name}:{scope_value}", float(next_count)
        if next_stake > max_stake:
            return f"{scope_name.upper()}_STAKE_LIMIT", f"{scope_name}:{scope_value}", next_stake
    return None


def _record_exposure(
    candidate: dict[str, Any],
    selected_count_by_scope: dict[tuple[str, str], int],
    selected_stake_by_scope: dict[tuple[str, str], float],
) -> None:
    stake = float(candidate.get("stake_units") or 0.0)
    scopes = [
        ("league", str(candidate.get("league") or "unknown")),
        ("market_family", str(candidate.get("market_family") or market_family(candidate))),
    ]
    exposure_parts = []
    exposure_values = []
    for scope_name, scope_value in scopes:
        key = (scope_name, scope_value)
        selected_count_by_scope[key] = selected_count_by_scope.get(key, 0) + 1
        selected_stake_by_scope[key] = selected_stake_by_scope.get(key, 0.0) + stake
        exposure_values.append(selected_stake_by_scope[key])
        exposure_parts.append(f"{scope_name}:{scope_value}={selected_stake_by_scope[key]:.2f}u")
    candidate["portfolio_exposure_scope"] = "|".join(exposure_parts)
    candidate["portfolio_exposure_after"] = round(max(exposure_values) if exposure_values else stake, 4)
