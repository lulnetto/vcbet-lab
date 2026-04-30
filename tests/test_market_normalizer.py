from __future__ import annotations

import unittest

from vcbet.core.market_normalizer import normalize_betano_market_contract


class DrawNoBetNormalizerTest(unittest.TestCase):
    def _market(self) -> dict:
        return {
            "typeId": 10,
            "name": "Empate Anula",
            "type": "Draw No Bet",
        }

    def test_typeid_10_home_selection(self) -> None:
        contract = normalize_betano_market_contract(
            self._market(),
            {"name": "Leeds United", "price": 1.70},
            "Leeds United",
            "Burnley",
        )

        self.assertEqual(contract["normalized_status"], "ok")
        self.assertEqual(contract["market_type"], "draw_no_bet")
        self.assertEqual(contract["market_scope"], "full_time")
        self.assertEqual(contract["side"], "home")
        self.assertEqual(contract["target_team_role"], "home")
        self.assertEqual(contract["target_team_name"], "Leeds United")
        self.assertEqual(contract["line"], 0.0)

    def test_typeid_10_away_selection(self) -> None:
        contract = normalize_betano_market_contract(
            self._market(),
            {"name": "Burnley", "price": 2.10},
            "Leeds United",
            "Burnley",
        )

        self.assertEqual(contract["normalized_status"], "ok")
        self.assertEqual(contract["market_type"], "draw_no_bet")
        self.assertEqual(contract["side"], "away")
        self.assertEqual(contract["target_team_role"], "away")
        self.assertEqual(contract["target_team_name"], "Burnley")
        self.assertEqual(contract["line"], 0.0)

    def test_typeid_10_invalid_selection(self) -> None:
        for selection_name in ("Empate", "Outro Time"):
            with self.subTest(selection_name=selection_name):
                contract = normalize_betano_market_contract(
                    self._market(),
                    {"name": selection_name, "price": 3.20},
                    "Leeds United",
                    "Burnley",
                )

                self.assertEqual(contract["normalized_status"], "unparseable_selection")
                self.assertEqual(contract["unsupported_reason"], "dnb_team_not_matched")


if __name__ == "__main__":
    unittest.main()
