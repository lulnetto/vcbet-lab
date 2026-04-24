from __future__ import annotations

import unittest

import pandas as pd

from vcbet.core.pick_features import build_candidate_row
from vcbet.service.dashboard import build_dashboard_payload


class PricingOutputTest(unittest.TestCase):
    def test_candidate_and_dashboard_payload_carry_corrected_pricing_fields(self) -> None:
        row = pd.Series(
            {
                "league": "Liga Teste",
                "match_datetime": "2026-04-24 15:00",
                "home_team": "Casa FC",
                "away_team": "Fora FC",
                "match_name": "Casa FC - Fora FC",
                "market_type": "asian_handicap",
                "market_scope": "full_time",
                "market_raw": "Handicap Asiático",
                "selection_raw": "Casa FC 0.0",
                "line": 0.0,
                "side": "home",
                "target_team_role": "home",
                "target_team_name": "Casa FC",
                "event_url": "https://example.test/match",
                "odd": 2.0,
            }
        )
        pricing_result = {
            "probs": {"win": 0.40, "half_win": 0.0, "push": 0.30, "half_loss": 0.0, "loss": 0.30},
            "mu_target": None,
            "mu_total": 2.5,
        }
        home_xg = pd.Series({"xg": 1.0, "xga": 1.1, "xg_home": 1.3, "xg_away": 0.9, "xga_home": 1.0, "xga_away": 1.2})
        away_xg = pd.Series({"xg": 1.0, "xga": 1.1, "xg_home": 1.2, "xg_away": 1.1, "xga_home": 1.3, "xga_away": 1.0})

        candidate = build_candidate_row(
            run_id="run_test",
            odds_run_id="run_test",
            xg_run_id="run_test",
            generated_at="2026-04-24 12:00:00",
            row=row,
            home_match_status="auto_exact",
            away_match_status="auto_exact",
            lambda_bundle={"lambda_home": 1.25, "lambda_away": 1.25, "mu_total": 2.5},
            pricing_result=pricing_result,
            home_xg_row=home_xg,
            away_xg_row=away_xg,
        )

        self.assertAlmostEqual(candidate["odd_justa"], 1.75)
        self.assertAlmostEqual(candidate["prob_model"], 1 / 1.75, places=6)
        self.assertAlmostEqual(candidate["ev_decimal"], 0.10)

        ledger_like = pd.DataFrame(
            [
                {
                    **candidate,
                    "bet_id": "bet_test",
                    "created_at": "2026-04-24 12:00:00",
                    "ev_percent": round(candidate["ev_decimal"] * 100, 2),
                    "stake_units": 1.0,
                    "final_bet_status": "open",
                    "final_settlement_status": "pending",
                    "pick_safety_status": "safe",
                    "candidate_stage": "official_accepted_pick",
                    "safety_gate_reason": "",
                    "risk_flags": "SEM_FLAG",
                }
            ]
        )

        payload = build_dashboard_payload(ledger_like, entries_limit=10)

        self.assertEqual(payload["entries"][0]["odd_justa"], 1.75)
        self.assertEqual(payload["entries"][0]["ev_percent"], 10.0)


if __name__ == "__main__":
    unittest.main()
