from __future__ import annotations

import unittest

from vcbet.core.pricing_engine import (
    effective_model_probability,
    expected_value_decimal,
    fair_odd_from_probs,
    price_market_selection,
    price_market_selection_result,
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

    def test_asian_total_zero_seventy_five_prices_half_results(self) -> None:
        over = price_market_selection(
            market_type="asian_total",
            side="over",
            line=0.75,
            target_team_role="geral",
            lambda_home=0.65,
            lambda_away=0.55,
        )
        under = price_market_selection(
            market_type="asian_total",
            side="under",
            line=0.75,
            target_team_role="geral",
            lambda_home=0.65,
            lambda_away=0.55,
        )

        self.assertIsNotNone(over)
        self.assertIsNotNone(under)
        assert over is not None
        assert under is not None
        self.assertGreater(over["probs"]["half_win"], 0.0)
        self.assertEqual(over["probs"]["half_loss"], 0.0)
        self.assertGreater(under["probs"]["half_loss"], 0.0)
        self.assertEqual(under["probs"]["half_win"], 0.0)
        self.assertAlmostEqual(sum(over["probs"].values()), 1.0)
        self.assertAlmostEqual(sum(under["probs"].values()), 1.0)

    def test_asian_total_one_twenty_five_prices_half_results(self) -> None:
        over = price_market_selection(
            market_type="asian_total",
            side="over",
            line=1.25,
            target_team_role="geral",
            lambda_home=0.75,
            lambda_away=0.65,
        )
        under = price_market_selection(
            market_type="asian_total",
            side="under",
            line=1.25,
            target_team_role="geral",
            lambda_home=0.75,
            lambda_away=0.65,
        )

        self.assertIsNotNone(over)
        self.assertIsNotNone(under)
        assert over is not None
        assert under is not None
        self.assertGreater(over["probs"]["half_loss"], 0.0)
        self.assertEqual(over["probs"]["half_win"], 0.0)
        self.assertGreater(under["probs"]["half_win"], 0.0)
        self.assertEqual(under["probs"]["half_loss"], 0.0)
        fair_odd = fair_odd_from_probs(over["probs"])
        assert fair_odd is not None
        self.assertAlmostZero(expected_value_decimal(over["probs"], fair_odd))

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

    def test_scalar_pricing_result_matches_existing_dict_api(self) -> None:
        legacy = price_market_selection(
            market_type="asian_total",
            side="over",
            line=2.75,
            target_team_role="geral",
            lambda_home=1.4,
            lambda_away=1.2,
        )
        result = price_market_selection_result(
            market_type="asian_total",
            side="over",
            line=2.75,
            target_team_role="geral",
            lambda_home=1.4,
            lambda_away=1.2,
            odd_decimal=2.05,
        )

        self.assertIsNotNone(legacy)
        self.assertIsNotNone(result)
        assert legacy is not None
        assert result is not None
        self.assertAlmostEqual(result.prob_model, effective_model_probability(legacy["probs"]))
        self.assertAlmostEqual(result.fair_odds, fair_odd_from_probs(legacy["probs"]))
        self.assertAlmostEqual(result.ev_percent, expected_value_decimal(legacy["probs"], 2.05) * 100)
        self.assertEqual(result.lambda_home, 1.4)
        self.assertEqual(result.lambda_away, 1.2)
        self.assertEqual(result.lambda_val, legacy["mu_target"])

    def test_pricing_engine_does_not_import_pandas(self) -> None:
        import vcbet.core.pricing_engine as pricing_engine

        self.assertNotIn("pandas", pricing_engine.__dict__)
        self.assertNotIn("pd", pricing_engine.__dict__)


if __name__ == "__main__":
    unittest.main()
