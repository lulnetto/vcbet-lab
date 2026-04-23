from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class MarketThreshold:
    market_type: str
    odd_min: float
    standard_max: float
    extended_max: float
    edge_min: float
    edge_strong: float
    edge_premium_extended: float
    is_primary_market: bool = False


MARKET_THRESHOLDS: Dict[str, MarketThreshold] = {
    "total_goals": MarketThreshold(
        market_type="total_goals",
        odd_min=1.65,
        standard_max=2.60,
        extended_max=3.20,
        edge_min=0.06,
        edge_strong=0.10,
        edge_premium_extended=0.12,
        is_primary_market=True,
    ),
    "team_total": MarketThreshold(
        market_type="team_total",
        odd_min=1.70,
        standard_max=2.60,
        extended_max=3.00,
        edge_min=0.07,
        edge_strong=0.10,
        edge_premium_extended=0.12,
        is_primary_market=False,
    ),
    "btts": MarketThreshold(
        market_type="btts",
        odd_min=1.70,
        standard_max=2.40,
        extended_max=2.80,
        edge_min=0.07,
        edge_strong=0.10,
        edge_premium_extended=0.12,
        is_primary_market=False,
    ),
    "asian_total": MarketThreshold(
        market_type="asian_total",
        odd_min=1.70,
        standard_max=2.60,
        extended_max=3.00,
        edge_min=0.06,
        edge_strong=0.10,
        edge_premium_extended=0.12,
        is_primary_market=True,
    ),
    "asian_handicap": MarketThreshold(
        market_type="asian_handicap",
        odd_min=1.70,
        standard_max=2.60,
        extended_max=3.00,
        edge_min=0.07,
        edge_strong=0.10,
        edge_premium_extended=0.12,
        is_primary_market=True,
    ),
}

CHAOTIC_LEAGUES = {"Championship", "Serie B", "Ligue 2", "Segunda División"}
PRIMARY_MARKETS = {name for name, cfg in MARKET_THRESHOLDS.items() if cfg.is_primary_market}
ALLOWED_MARKETS = set(MARKET_THRESHOLDS.keys())
MARKET_PRIORITY = {
    "total_goals": 1,
    "asian_total": 2,
    "asian_handicap": 3,
    "btts": 4,
    "team_total": 5,
}

CRITICAL_FLAGS = {"MATCH_DUVIDOSO", "DADO_INCOMPLETO_LIGA"}
CONFIDENCE_CAPS = {
    "MATCH_FUZZY": 4,
    "ODD_ALTA_VARIANCIA": 4,
    "MERCADO_TIME": 4,
    "LIGA_VOLATIL": 4,
    "DRAW_SENSITIVE_LINE": 4,
    "CORRELACAO_JOGO": 3,
    "LINHA_EXTREMA": 3,
    "POISSON_MARGIN_RISK": 3,
}


def get_market_threshold(market_type: str) -> MarketThreshold:
    return MARKET_THRESHOLDS[market_type]
