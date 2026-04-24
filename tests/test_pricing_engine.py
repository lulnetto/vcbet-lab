from __future__ import annotations

import unittest

from vcbet.core.pricing_engine import (
    effective_model_probability,
    expected_value_decimal,
    fair_odd_from_probs,
    price_market_selection,
)


class PricingEngineTest(unittest.TestCase):
    def assertAlmostZero(self, value: float, places: int = 9) -> None:
        self.assertAlmostEqual(value, 0.0, places=places)

    def test_fair_odd_accounts_for_push_probability(self) -> None:
        probs = {"win": 0.40, "half_win": 0.0, "push": 0.30, "half_loss": 0.0, "loss": 0.30}

        fair_odd = fair_odd_from_probs(probs)

        self.assertAlmostEqual(fair_odd, 1.75)
        self.assertAlmostEqual(effective_model_probability(probs), 1 / 1.75)
        assert fair_odd is not None
        self.assertAlmostZero(expected_value_decimal(probs, fair_odd))

    def test_asian_handicap_zero_line_has_push_and_break_even_fair_odd(self) -> None:
        result = price_market_selection(
            market_type="asian_handicap",
            side="home",
            line=0.0,
            target_team_role="home",
            lambda_home=1.25,
            lambda_away=1.25,
        )

        self.assertIsNotNone(result)
        assert result is not None
        probs = result["probs"]
        self.assertGreater(probs["push"], 0.0)
        self.assertEqual(probs["half_win"], 0.0)
        self.assertEqual(probs["half_loss"], 0.0)
        fair_odd = fair_odd_from_probs(probs)
        assert fair_odd is not None
        self.assertLess(fair_odd, 1 / probs["win"])
        self.assertAlmostZero(expected_value_decimal(probs, fair_odd))

    def test_quarter_asian_lines_reflect_half_win_and_half_loss(self) -> None:
        plus_quarter = price_market_selection(
            market_type="asian_handicap",
            side="home",
            line=0.25,
            target_team_role="home",
            lambda_home=1.25,
            lambda_away=1.25,
        )
        minus_quarter = price_market_selection(
            market_type="asian_handicap",
            side="home",
            line=-0.25,
            target_team_role="home",
            lambda_home=1.25,
            lambda_away=1.25,
        )

        self.assertIsNotNone(plus_quarter)
        self.assertIsNotNone(minus_quarter)
        assert plus_quarter is not None
        assert minus_quarter is not None
        plus_probs = plus_quarter["probs"]
        minus_probs = minus_quarter["probs"]
        self.assertGreater(plus_probs["half_win"], 0.0)
        self.assertEqual(plus_probs["half_loss"], 0.0)
        self.assertGreater(minus_probs["half_loss"], 0.0)
        self.assertEqual(minus_probs["half_win"], 0.0)
        self.assertLess(fair_odd_from_probs(plus_probs), fair_odd_from_probs(minus_probs))

    def test_quarter_line_ev_moves_in_expected_direction(self) -> None:
        common = {
            "market_type": "asian_handicap",
            "side": "home",
            "target_team_role": "home",
            "lambda_home": 1.25,
            "lambda_away": 1.25,
        }
        plus_probs = price_market_selection(line=0.25, **common)["probs"]
        minus_probs = price_market_selection(line=-0.25, **common)["probs"]

        self.assertGreater(expected_value_decimal(plus_probs, 2.0), 0.0)
        self.assertLess(expected_value_decimal(minus_probs, 2.0), 0.0)
        self.assertGreater(
            expected_value_decimal(plus_probs, 2.0),
            expected_value_decimal(minus_probs, 2.0),
        )

    def test_binary_market_fair_odd_stays_inverse_probability(self) -> None:
        result = price_market_selection(
            market_type="btts",
            side="yes",
            line=None,
            target_team_role="geral",
            lambda_home=1.3,
            lambda_away=1.1,
        )

        self.assertIsNotNone(result)
        assert result is not None
        probs = result["probs"]
        self.assertEqual(probs["push"], 0.0)
        self.assertAlmostEqual(fair_odd_from_probs(probs), 1 / probs["win"])


if __name__ == "__main__":
    unittest.main()
