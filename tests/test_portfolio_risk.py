from __future__ import annotations

import unittest

import pandas as pd

from vcbet.core.line_selector import select_top_picks
from vcbet.core.strategy_config import configure_runtime, get_runtime_config
from vcbet.service.dashboard import build_dashboard_payload


def candidate(**overrides):
    payload = {
        "run_id": "run_test",
        "generated_at": "2026-04-24 12:00:00",
        "league": "Liga Teste",
        "match_datetime": "2026-04-24 15:00",
        "home_team": "Casa FC",
        "away_team": "Fora FC",
        "match_name": "Casa FC - Fora FC",
        "market_type": "total_goals",
        "market_scope": "full_time",
        "market_raw": "Total de Gols Mais/Menos",
        "selection_raw": "Mais de 2.5",
        "line": 2.5,
        "side": "over",
        "target_team_role": "geral",
        "target_team_name": "geral",
        "event_url": "https://example.test/match",
        "odd_entrada": 2.0,
        "odd_justa": 1.8,
        "prob_model": 0.55,
        "ev_decimal": 0.12,
        "ev_percent": 12.0,
        "confidence_score": 5,
        "stake_units": 1.0,
        "entry_reason": "EDGE_FORTE",
        "risk_flags": "SEM_FLAG",
        "pick_safety_status": "safe",
        "candidate_stage": "eligible_pick",
        "safety_gate_reason": "",
        "decision_policy_status": "eligible",
        "decision_reject_reason": "",
        "selection_policy_status": "selection_pending",
        "market_priority": 1,
        "bet_id": overrides.get("bet_id", "bet_test"),
    }
    payload.update(overrides)
    return payload


class PortfolioRiskTest(unittest.TestCase):
    def setUp(self) -> None:
        configure_runtime()

    def test_league_exposure_limit_rejects_traceably(self) -> None:
        runtime = get_runtime_config()
        runtime.rules["portfolio"]["max_picks_per_league"] = 1

        selected, rejected = select_top_picks(
            pd.DataFrame(
                [
                    candidate(bet_id="first", match_name="Casa FC - Fora FC"),
                    candidate(bet_id="second", match_name="Outro FC - Rival FC", home_team="Outro FC", away_team="Rival FC"),
                ]
            ),
            return_meta=True,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["portfolio_risk_status"], "rejected")
        self.assertEqual(rejected.iloc[0]["portfolio_risk_reason"], "LEAGUE_PICK_LIMIT")
        self.assertEqual(rejected.iloc[0]["portfolio_exposure_scope"], "league:Liga Teste")

    def test_market_family_exposure_limit_rejects_total_family(self) -> None:
        runtime = get_runtime_config()
        runtime.rules["portfolio"]["max_picks_per_market_family"] = 1

        selected, rejected = select_top_picks(
            pd.DataFrame(
                [
                    candidate(bet_id="total", match_name="Casa FC - Fora FC", market_type="total_goals", selection_raw="Mais de 2.5"),
                    candidate(bet_id="asian", match_name="Outro FC - Rival FC", home_team="Outro FC", away_team="Rival FC", market_type="asian_total", selection_raw="Mais de 2.75", line=2.75),
                ]
            ),
            return_meta=True,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["portfolio_risk_reason"], "MARKET_FAMILY_PICK_LIMIT")
        self.assertEqual(rejected.iloc[0]["portfolio_exposure_scope"], "market_family:goals_total")

    def test_near_duplicate_line_is_rejected_before_generic_correlation(self) -> None:
        selected, rejected = select_top_picks(
            pd.DataFrame(
                [
                    candidate(bet_id="total", market_type="total_goals", selection_raw="Mais de 2.5", line=2.5),
                    candidate(bet_id="asian", market_type="asian_total", selection_raw="Mais de 2.75", line=2.75),
                ]
            ),
            return_meta=True,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["portfolio_risk_reason"], "DUPLICATE_OR_NEAR_DUPLICATE")
        self.assertEqual(rejected.iloc[0]["candidate_stage"], "selection_rejected_candidate")

    def test_contradictory_line_is_rejected_traceably(self) -> None:
        selected, rejected = select_top_picks(
            pd.DataFrame(
                [
                    candidate(bet_id="over", selection_raw="Mais de 2.5", side="over", line=2.5),
                    candidate(bet_id="under", selection_raw="Menos de 2.5", side="under", line=2.5, odd_entrada=1.95),
                ]
            ),
            return_meta=True,
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["portfolio_risk_reason"], "CONTRADICTORY_LINE_WITH_SELECTED")
        self.assertIn("ref_side=", rejected.iloc[0]["portfolio_reject_details"])

    def test_medium_correlation_is_downgraded_not_silent(self) -> None:
        selected, rejected = select_top_picks(
            pd.DataFrame(
                [
                    candidate(bet_id="total", market_type="total_goals", selection_raw="Mais de 2.5", side="over", line=2.5),
                    candidate(
                        bet_id="handicap",
                        market_type="asian_handicap",
                        market_priority=3,
                        selection_raw="Casa FC -0.25",
                        side="home",
                        line=-0.25,
                        target_team_role="home",
                        target_team_name="Casa FC",
                    ),
                ]
            ),
            return_meta=True,
        )

        self.assertEqual(len(rejected), 0)
        self.assertEqual(len(selected), 2)
        secondary = selected.loc[selected["bet_id"] == "handicap"].iloc[0]
        self.assertEqual(secondary["portfolio_risk_status"], "downgraded")
        self.assertEqual(secondary["portfolio_risk_reason"], "MEDIUM_CORRELATION_DOWNGRADED")
        self.assertEqual(float(secondary["stake_units"]), 0.5)
        self.assertIn("CORRELACAO_JOGO", secondary["risk_flags"])

    def test_downstream_payload_keeps_portfolio_fields(self) -> None:
        row = {
            **candidate(bet_id="selected"),
            "created_at": "2026-04-24 12:00:00",
            "final_bet_status": "open",
            "final_settlement_status": "pending",
            "portfolio_risk_status": "accepted",
            "portfolio_risk_reason": "",
            "portfolio_exposure_scope": "league:Liga Teste=1.00u|market_family:goals_total=1.00u",
            "portfolio_exposure_after": 1.0,
            "market_family": "goals_total",
        }

        payload = build_dashboard_payload(pd.DataFrame([row]), entries_limit=10)

        self.assertEqual(payload["entries"][0]["portfolio_risk_status"], "accepted")
        self.assertEqual(payload["entries"][0]["market_family"], "goals_total")


if __name__ == "__main__":
    unittest.main()
