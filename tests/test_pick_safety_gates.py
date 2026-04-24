from __future__ import annotations

import unittest

from vcbet.core.pick_filter import evaluate_pick_candidate_with_details
from vcbet.core.strategy_config import configure_runtime


def base_candidate(**overrides):
    payload = {
        "run_id": "run_test",
        "odds_source_run_id": "run_test",
        "xg_source_run_id": "run_test",
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
        "odd_entrada": 2.2,
        "odd_justa": 1.75,
        "prob_model": 0.57,
        "ev_decimal": 0.20,
        "mu_total": 2.8,
        "lambda_home": 1.5,
        "lambda_away": 1.3,
        "match_status_home": "auto_exact",
        "match_status_away": "auto_exact",
        "xg_fallback_home": False,
        "xg_fallback_away": False,
    }
    payload.update(overrides)
    return payload


class PickSafetyGateTest(unittest.TestCase):
    def setUp(self) -> None:
        configure_runtime()

    def test_match_fuzzy_is_blocked_from_official_eligibility(self) -> None:
        candidate = base_candidate(match_status_home="auto_fuzzy_high")

        evaluated, reject_reason, blocked = evaluate_pick_candidate_with_details(candidate)

        self.assertIsNone(evaluated)
        self.assertEqual(reject_reason, "safety_gate_blocked")
        self.assertIsNotNone(blocked)
        assert blocked is not None
        self.assertEqual(blocked["pick_safety_status"], "blocked")
        self.assertEqual(blocked["candidate_stage"], "blocked_unsafe_candidate")
        self.assertIn("MATCH_FUZZY", blocked["risk_flags"])
        self.assertIn("MATCH_FUZZY", blocked["safety_gate_reason"])

    def test_exact_match_passes_as_safe_eligible_pick(self) -> None:
        evaluated, reject_reason, blocked = evaluate_pick_candidate_with_details(base_candidate())

        self.assertIsNone(reject_reason)
        self.assertIsNone(blocked)
        self.assertIsNotNone(evaluated)
        assert evaluated is not None
        self.assertEqual(evaluated["pick_safety_status"], "safe")
        self.assertEqual(evaluated["candidate_stage"], "eligible_pick")
        self.assertEqual(evaluated["safety_gate_reason"], "")

    def test_pending_or_blocked_match_status_is_safety_blocked_and_traceable(self) -> None:
        candidate = base_candidate(match_status_away="pending_review")

        evaluated, reject_reason, blocked = evaluate_pick_candidate_with_details(candidate)

        self.assertIsNone(evaluated)
        self.assertEqual(reject_reason, "safety_gate_blocked")
        self.assertIsNotNone(blocked)
        assert blocked is not None
        self.assertEqual(blocked["pick_safety_status"], "blocked")
        self.assertIn("MATCH_DUVIDOSO", blocked["safety_gate_reason"])
        self.assertEqual(blocked["safety_reject_reason"], "safety_gate_blocked")


if __name__ == "__main__":
    unittest.main()
