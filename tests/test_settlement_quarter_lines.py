from __future__ import annotations

import unittest

from vcbet.settlement.settlement_engine import (
    compute_result_units,
    settle_asian_handicap,
    settle_total_like,
)


class SettlementQuarterLineTest(unittest.TestCase):
    def test_total_zero_seventy_five_half_and_full_outcomes(self) -> None:
        self.assertEqual(settle_total_like("over", 0.75, 0), "loss")
        self.assertEqual(settle_total_like("over", 0.75, 1), "half_win")
        self.assertEqual(settle_total_like("over", 0.75, 2), "win")
        self.assertEqual(settle_total_like("under", 0.75, 0), "win")
        self.assertEqual(settle_total_like("under", 0.75, 1), "half_loss")
        self.assertEqual(settle_total_like("under", 0.75, 2), "loss")

    def test_total_one_twenty_five_half_and_full_outcomes(self) -> None:
        self.assertEqual(settle_total_like("over", 1.25, 0), "loss")
        self.assertEqual(settle_total_like("over", 1.25, 1), "half_loss")
        self.assertEqual(settle_total_like("over", 1.25, 2), "win")
        self.assertEqual(settle_total_like("under", 1.25, 0), "win")
        self.assertEqual(settle_total_like("under", 1.25, 1), "half_win")
        self.assertEqual(settle_total_like("under", 1.25, 2), "loss")

    def test_asian_handicap_quarter_lines_split_stake_outcomes(self) -> None:
        self.assertEqual(settle_asian_handicap("home", 0.75, 0, 2), "loss")
        self.assertEqual(settle_asian_handicap("home", 0.75, 0, 1), "half_loss")
        self.assertEqual(settle_asian_handicap("home", 0.75, 0, 0), "win")
        self.assertEqual(settle_asian_handicap("home", -1.25, 1, 0), "half_loss")
        self.assertEqual(settle_asian_handicap("home", -1.25, 2, 0), "win")

    def test_result_units_cover_half_win_half_loss_and_push(self) -> None:
        self.assertEqual(compute_result_units("half_win", odd=2.5, stake_units=2.0), 1.5)
        self.assertEqual(compute_result_units("half_loss", odd=2.5, stake_units=2.0), -1.0)
        self.assertEqual(compute_result_units("push", odd=2.5, stake_units=2.0), 0.0)


if __name__ == "__main__":
    unittest.main()
