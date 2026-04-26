from __future__ import annotations

import math
from typing import Any

from scipy.stats import poisson

from vcbet.domain.contracts import PricingResult


def calculate_lambdas(xg_home: float, xga_home: float, xg_away: float, xga_away: float) -> dict[str, float]:
    lambda_home = max((float(xg_home) + float(xga_away)) / 2, 0.01)
    lambda_away = max((float(xg_away) + float(xga_home)) / 2, 0.01)
    return {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "mu_total": lambda_home + lambda_away,
    }


def expected_value_decimal(probs: dict[str, float], odd_decimal: float) -> float:
    b = odd_decimal - 1.0
    return (
        probs["win"] * b
        + probs["half_win"] * (b / 2)
        - probs["half_loss"] * 0.5
        - probs["loss"]
    )


def _outcome_prob(probs: dict[str, float], outcome: str) -> float:
    return float(probs.get(outcome, 0.0) or 0.0)


def effective_model_probability(probs: dict[str, float]) -> float:
    fair_odd = fair_odd_from_probs(probs)
    if fair_odd is None or fair_odd <= 0:
        return 0.0
    return 1.0 / fair_odd


def fair_profit_loss_ratio_from_probs(probs: dict[str, float]) -> float | None:
    win_equivalent = _outcome_prob(probs, "win") + 0.5 * _outcome_prob(probs, "half_win")
    loss_equivalent = _outcome_prob(probs, "loss") + 0.5 * _outcome_prob(probs, "half_loss")
    if win_equivalent <= 0:
        return None
    return loss_equivalent / win_equivalent


def fair_odd_from_probs(probs: dict[str, float]) -> float | None:
    fair_profit_loss_ratio = fair_profit_loss_ratio_from_probs(probs)
    if fair_profit_loss_ratio is None:
        return None
    return 1.0 + fair_profit_loss_ratio


def pricing_result_from_probs(
    *,
    probs: dict[str, float],
    odd_decimal: float,
    lambda_home: float | None = None,
    lambda_away: float | None = None,
    lambda_val: float | None = None,
    method: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PricingResult | None:
    fair_odd = fair_odd_from_probs(probs)
    if fair_odd is None:
        return None
    return PricingResult(
        prob_model=effective_model_probability(probs),
        fair_odds=fair_odd,
        ev_percent=expected_value_decimal(probs, float(odd_decimal)) * 100,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        lambda_val=lambda_val,
        method=method,
        model=model,
        metadata=metadata or {},
    )


def _univariate_probs(mu: float, side: str, line: float) -> dict[str, float] | None:
    frac = round(line % 1, 2)
    base = int(math.floor(line))

    p_win = p_half_win = p_push = p_half_loss = p_loss = 0.0

    if frac == 0.5:
        if side == "over":
            p_win = 1 - poisson.cdf(base, mu)
            p_loss = poisson.cdf(base, mu)
        elif side == "under":
            p_win = poisson.cdf(base, mu)
            p_loss = 1 - poisson.cdf(base, mu)
        else:
            return None

    elif frac == 0.0:
        p_exact = poisson.pmf(base, mu)
        if side == "over":
            p_loss = poisson.cdf(base - 1, mu) if base > 0 else 0
            p_push = p_exact
            p_win = 1 - poisson.cdf(base, mu)
        elif side == "under":
            p_win = poisson.cdf(base - 1, mu) if base > 0 else 0
            p_push = p_exact
            p_loss = 1 - poisson.cdf(base, mu)
        else:
            return None

    elif frac == 0.25:
        p_exact = poisson.pmf(base, mu)
        if side == "over":
            p_loss = poisson.cdf(base - 1, mu) if base > 0 else 0
            p_half_loss = p_exact
            p_win = 1 - poisson.cdf(base, mu)
        elif side == "under":
            p_win = poisson.cdf(base - 1, mu) if base > 0 else 0
            p_half_win = p_exact
            p_loss = 1 - poisson.cdf(base, mu)
        else:
            return None

    elif frac == 0.75:
        base_next = base + 1
        p_exact = poisson.pmf(base_next, mu)
        if side == "over":
            p_loss = poisson.cdf(base, mu)
            p_half_win = p_exact
            p_win = 1 - poisson.cdf(base_next, mu)
        elif side == "under":
            p_win = poisson.cdf(base, mu)
            p_half_loss = p_exact
            p_loss = 1 - poisson.cdf(base_next, mu)
        else:
            return None
    else:
        return None

    return {
        "win": max(p_win, 0.0),
        "half_win": max(p_half_win, 0.0),
        "push": max(p_push, 0.0),
        "half_loss": max(p_half_loss, 0.0),
        "loss": max(p_loss, 0.0),
    }


def _settle_single_ah_component(goal_diff: int, side: str, line: float) -> str:
    adjusted = goal_diff + line if side == "home" else (-goal_diff) + line
    if adjusted > 0:
        return "win"
    if adjusted < 0:
        return "loss"
    return "push"


def _split_asian_line(line: float) -> list[float]:
    frac = round(abs(line) % 1, 2)
    if frac in {0.0, 0.5}:
        return [line]
    if frac in {0.25, 0.75}:
        return [line - 0.25, line + 0.25]
    return [line]


def _combine_component_results(results: list[str]) -> str:
    if len(results) == 1:
        return results[0]
    unique = tuple(sorted(results))
    if unique == ("loss", "loss"):
        return "loss"
    if unique == ("win", "win"):
        return "win"
    if unique == ("push", "win"):
        return "half_win"
    if unique == ("loss", "push"):
        return "half_loss"
    if unique == ("push", "push"):
        return "push"
    return "loss"


def _asian_handicap_probs(lambda_home: float, lambda_away: float, side: str, line: float, max_goals: int | None = None) -> dict[str, float]:
    if side not in {"home", "away"}:
        return None

    max_goals = max_goals or int(max(10, math.ceil(max(lambda_home, lambda_away) + 8 * math.sqrt(max(lambda_home, lambda_away) + 1))))
    probs = {"win": 0.0, "half_win": 0.0, "push": 0.0, "half_loss": 0.0, "loss": 0.0}
    components = _split_asian_line(line)

    for goals_home in range(max_goals + 1):
        p_home = poisson.pmf(goals_home, lambda_home)
        for goals_away in range(max_goals + 1):
            p_away = poisson.pmf(goals_away, lambda_away)
            probability = p_home * p_away
            result = _combine_component_results(
                [_settle_single_ah_component(goals_home - goals_away, side, comp_line) for comp_line in components]
            )
            probs[result] += probability

    total = sum(probs.values())
    if total > 0:
        probs = {key: value / total for key, value in probs.items()}
    return probs


def price_market_selection(
    *,
    market_type: str,
    side: str,
    line: float | None,
    target_team_role: str,
    lambda_home: float,
    lambda_away: float,
) -> dict[str, Any] | None:
    mu_total = lambda_home + lambda_away

    if market_type == "btts":
        p_yes = (1 - poisson.pmf(0, lambda_home)) * (1 - poisson.pmf(0, lambda_away))
        if side == "yes":
            probs = {"win": p_yes, "half_win": 0.0, "push": 0.0, "half_loss": 0.0, "loss": 1 - p_yes}
        elif side == "no":
            probs = {"win": 1 - p_yes, "half_win": 0.0, "push": 0.0, "half_loss": 0.0, "loss": p_yes}
        else:
            return None
        return {"probs": probs, "mu_target": None, "mu_total": mu_total}

    if market_type in {"total_goals", "asian_total"}:
        if line is None or side not in {"over", "under"}:
            return None
        probs = _univariate_probs(mu_total, side, float(line))
        if probs is None:
            return None
        return {"probs": probs, "mu_target": mu_total, "mu_total": mu_total}

    if market_type == "team_total":
        if line is None or side not in {"over", "under"}:
            return None
        if target_team_role == "home":
            mu_target = lambda_home
        elif target_team_role == "away":
            mu_target = lambda_away
        else:
            return None
        probs = _univariate_probs(mu_target, side, float(line))
        if probs is None:
            return None
        return {"probs": probs, "mu_target": mu_target, "mu_total": mu_total}

    if market_type == "asian_handicap":
        if line is None or side not in {"home", "away"}:
            return None
        probs = _asian_handicap_probs(lambda_home, lambda_away, side, float(line))
        if probs is None:
            return None
        return {"probs": probs, "mu_target": None, "mu_total": mu_total}

    return None


def price_market_selection_result(
    *,
    market_type: str,
    side: str,
    line: float | None,
    target_team_role: str,
    lambda_home: float,
    lambda_away: float,
    odd_decimal: float,
) -> PricingResult | None:
    priced = price_market_selection(
        market_type=market_type,
        side=side,
        line=line,
        target_team_role=target_team_role,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
    )
    if not priced:
        return None
    return pricing_result_from_probs(
        probs=priced["probs"],
        odd_decimal=odd_decimal,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        lambda_val=priced["mu_target"],
        method=market_type,
        model="poisson",
        metadata={"mu_total": priced["mu_total"], "probs": priced["probs"]},
    )
