from __future__ import annotations

import unittest

from vcbet.core.pricing_engine import fair_odd_from_probs, price_draw_no_bet


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


if __name__ == "__main__":
    unittest.main()
