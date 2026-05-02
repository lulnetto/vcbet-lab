from __future__ import annotations

import unittest

import pandas as pd

from vcbet.core.ledger_portfolio_gate import check_against_open_ledger


def _ledger_row(**overrides) -> dict:
    base = {
        "bet_id": "ledger_dnb",
        "run_id": "run_existing",
        "config_name": "test",
        "league": "Liga Test",
        "match_datetime": "2026-05-01 15:00",
        "home_team": "Real Zaragoza",
        "away_team": "Granada",
        "match_name": "Real Zaragoza - Granada",
        "event_url": "http://example.com/zaragoza-granada",
        "market_type": "draw_no_bet",
        "market_scope": "full_time",
        "target_team_role": "away",
        "target_team_name": "Granada",
        "side": "away",
        "line": 0.0,
        "selection_raw": "Granada",
        "final_bet_status": "open",
        "final_settlement_status": "pending",
    }
    base.update(overrides)
    return base


class LedgerPortfolioGateCorrelationTest(unittest.TestCase):
    def test_existing_dnb_blocks_new_ah_zero_same_team(self) -> None:
        ledger = pd.DataFrame([_ledger_row()])
        candidate = _ledger_row(
            bet_id="new_ah0",
            run_id="run_new",
            market_type="asian_handicap",
            line=0.0,
            selection_raw="Granada 0.0",
        )

        gate = check_against_open_ledger(candidate, ledger)

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["reason"], "EQUIVALENT_MARKET_ALREADY_IN_LEDGER")
        self.assertEqual(gate["related_bet_id"], "ledger_dnb")
        self.assertIn("DNB_EQUALS_AH_0", gate["details"])


if __name__ == "__main__":
    unittest.main()
