from __future__ import annotations

import unittest
from types import SimpleNamespace

import pandas as pd

from vcbet.core.pricing_engine import fair_odd_from_probs, price_draw_no_bet
from vcbet.core.xg_residuals import (
    XG_RESIDUAL_ADJUSTED_PRICING_VARIANT,
    build_xg_residual_pricing_setup,
    calculate_team_residual_adjustment,
)


class DrawNoBetPricingTest(unittest.TestCase):
    def test_price_draw_no_bet_uses_draw_as_push(self) -> None:
        home = price_draw_no_bet(lambda_home=1.6, lambda_away=1.0, side="home")
        away = price_draw_no_bet(lambda_home=1.6, lambda_away=1.0, side="away")

        self.assertIsNotNone(home)
        self.assertIsNotNone(away)

        home_probs = home["probs"]
        away_probs = away["probs"]
        home_fair = fair_odd_from_probs(home_probs)
        away_fair = fair_odd_from_probs(away_probs)

        self.assertLess(home_fair, away_fair)
        self.assertLess(home_fair, 1 / home_probs["win"])
        self.assertAlmostEqual(home_fair, 1 + home_probs["loss"] / home_probs["win"], places=10)
        self.assertAlmostEqual(away_fair, 1 + away_probs["loss"] / away_probs["win"], places=10)
        self.assertGreater(home_probs["push"], 0)


class XGResidualAdjustmentTest(unittest.TestCase):
    def test_team_residual_calculation_shrinks_and_caps(self) -> None:
        row = {
            "xg": 2.0,
            "xga": 1.0,
            "goals_for_per_match": 1.6,
            "goals_against_per_match": 1.3,
            "xg_raw_total": 40.0,
            "xga_raw_total": 20.0,
        }
        cfg = {
            "enabled": True,
            "weight": 0.25,
            "max_residual_abs": 0.35,
            "max_lambda_adjustment_pct": 0.07,
            "shrink_prior_games": 12,
            "min_games": 8,
        }

        adjusted = calculate_team_residual_adjustment(row, cfg)

        self.assertAlmostEqual(adjusted["attack_residual"], -0.4)
        self.assertAlmostEqual(adjusted["defense_residual"], 0.3)
        self.assertAlmostEqual(adjusted["attack_residual_clamped"], -0.35)
        self.assertGreater(adjusted["residual_shrink"], 0)
        self.assertLess(adjusted["adjusted_attack_xg"], row["xg"])
        self.assertGreater(adjusted["adjusted_defense_xga"], row["xga"])
        self.assertLessEqual(abs(adjusted["adjusted_attack_xg"] - row["xg"]) / row["xg"], 0.07)
        self.assertLessEqual(abs(adjusted["adjusted_defense_xga"] - row["xga"]) / row["xga"], 0.07)

    def test_lambda_adjustment_is_capped(self) -> None:
        runtime = SimpleNamespace(
            payload={
                "pricing_variant": XG_RESIDUAL_ADJUSTED_PRICING_VARIANT,
                "xg_residual_adjustment": {
                    "enabled": True,
                    "weight": 10.0,
                    "max_residual_abs": 5.0,
                    "max_lambda_adjustment_pct": 0.07,
                    "shrink_prior_games": 0,
                    "min_games": 1,
                    "markets": ["total_goals"],
                },
            }
        )
        home = pd.Series(
            {
                "xg": 1.0,
                "xga": 1.0,
                "xg_home": 1.0,
                "xga_home": 1.0,
                "goals_for_per_match": 8.0,
                "goals_against_per_match": 0.1,
                "xg_raw_total": 20.0,
                "xga_raw_total": 20.0,
            }
        )
        away = pd.Series(
            {
                "xg": 1.0,
                "xga": 1.0,
                "xg_away": 1.0,
                "xga_away": 1.0,
                "goals_for_per_match": 8.0,
                "goals_against_per_match": 0.1,
                "xg_raw_total": 20.0,
                "xga_raw_total": 20.0,
            }
        )

        setup = build_xg_residual_pricing_setup(
            home_xg_row=home,
            away_xg_row=away,
            market_type="total_goals",
            runtime_config=runtime,
        )

        self.assertLessEqual(abs(setup["diagnostics"]["lambda_home_adjustment_pct"]), 0.07 + 1e-12)
        self.assertLessEqual(abs(setup["diagnostics"]["lambda_away_adjustment_pct"]), 0.07 + 1e-12)


if __name__ == "__main__":
    unittest.main()
