from __future__ import annotations

from typing import Any

from vcbet.core.selection import market_family


def _cap_enabled(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"", "0", "0.0", "none", "null", "disabled", "false"}:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _cap_float(value: Any) -> float | None:
    if not _cap_enabled(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _exposure_rejection(
    candidate: dict[str, Any],
    selected_count_by_scope: dict[tuple[str, str], int],
    selected_stake_by_scope: dict[tuple[str, str], float],
    portfolio_rules: dict[str, Any],
) -> tuple[str, str, float] | None:
    # Liga/família deixaram de ser gates duros de portfolio. A exposição
    # continua sendo registrada em _record_exposure para auditoria.
    return None


def _record_exposure(
    candidate: dict[str, Any],
    selected_count_by_scope: dict[tuple[str, str], int],
    selected_stake_by_scope: dict[tuple[str, str], float],
    portfolio_rules: dict[str, Any] | None = None,
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

    if not portfolio_rules:
        return

    warning_parts = []
    checks = [
        (
            "league",
            str(candidate.get("league") or "unknown"),
            _cap_float(portfolio_rules.get("max_picks_per_league")),
            _cap_float(portfolio_rules.get("max_stake_per_league")),
        ),
        (
            "market_family",
            str(candidate.get("market_family") or market_family(candidate)),
            _cap_float(portfolio_rules.get("max_picks_per_market_family")),
            _cap_float(portfolio_rules.get("max_stake_per_market_family")),
        ),
    ]
    for scope_name, scope_value, max_count, max_stake in checks:
        key = (scope_name, scope_value)
        count = selected_count_by_scope.get(key, 0)
        stake_after = selected_stake_by_scope.get(key, 0.0)
        if max_count is not None and count > max_count:
            warning_parts.append(f"{scope_name.upper()}_PICK_LIMIT_METRIC:{count}>{max_count:g}")
        if max_stake is not None and stake_after > max_stake:
            warning_parts.append(f"{scope_name.upper()}_STAKE_LIMIT_METRIC:{stake_after:.2f}>{max_stake:g}")
    candidate["portfolio_exposure_warning"] = "|".join(warning_parts)
