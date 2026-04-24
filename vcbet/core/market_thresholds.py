from __future__ import annotations

from vcbet.core.strategy_config import MarketThreshold, get_runtime_config


def get_market_threshold(market_type: str) -> MarketThreshold:
    return get_runtime_config().markets[market_type]


def get_primary_markets() -> set[str]:
    return get_runtime_config().primary_markets


def get_allowed_markets() -> set[str]:
    return get_runtime_config().allowed_markets


def get_market_priority() -> dict[str, int]:
    return get_runtime_config().market_priority


def get_critical_flags() -> set[str]:
    return get_runtime_config().critical_flags


def get_confidence_caps() -> dict[str, int]:
    return get_runtime_config().confidence_caps


def get_confidence_penalties() -> dict[str, int]:
    return get_runtime_config().confidence_penalties
