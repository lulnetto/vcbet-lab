from __future__ import annotations

import unittest

import pandas as pd

from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.line_selector import select_top_picks
from vcbet.core.selection.line_selection import select_top_picks as select_top_candidate_dicts
from vcbet.core.pricing_engine import expected_value_decimal, price_market_selection
from vcbet.core.risk_policy import assess_risk_flags, safety_gate_flags
from vcbet.core.strategy_config import configure_runtime
from vcbet.service.dashboard import build_dashboard_payload


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
        "prob_model": 0.571429,
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


class DecisionArchitectureTest(unittest.TestCase):
    def setUp(self) -> None:
        configure_runtime()

    def test_pricing_remains_callable_without_decision_policy(self) -> None:
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
        self.assertGreater(result["probs"]["push"], 0.0)
        self.assertIsInstance(expected_value_decimal(result["probs"], 2.0), float)

    def test_decision_policy_rejects_value_without_mutating_pricing_fields(self) -> None:
        candidate = base_candidate(ev_decimal=0.01, odd_justa=1.75, prob_model=0.571429)

        evaluated, reject_reason, rejected = evaluate_pick_candidate_with_details(candidate)

        self.assertIsNone(evaluated)
        self.assertEqual(reject_reason, "edge_below_min")
        self.assertIsNone(rejected)
        self.assertEqual(candidate["ev_decimal"], 0.01)
        self.assertEqual(candidate["odd_justa"], 1.75)
        self.assertEqual(candidate["prob_model"], 0.571429)

    def test_ev_outlier_above_max_is_rejected_explicitly(self) -> None:
        candidate = base_candidate(ev_decimal=0.25, odd_entrada=2.5)

        evaluated, reject_reason, rejected = evaluate_pick_candidate_with_details(candidate)

        self.assertIsNone(evaluated)
        self.assertEqual(reject_reason, "ev_outlier_above_max")
        self.assertIsNotNone(rejected)
        assert rejected is not None
        self.assertEqual(rejected["decision_reject_reason"], "ev_outlier_above_max")

    def test_ev_at_max_boundary_passes(self) -> None:
        candidate = base_candidate(ev_decimal=0.20, odd_entrada=2.2)

        evaluated, reject_reason, rejected = evaluate_pick_candidate_with_details(candidate)

        self.assertIsNotNone(evaluated)
        self.assertIsNone(reject_reason)
        self.assertIsNone(rejected)

    def test_risk_policy_blocking_is_distinct_from_value_rejection(self) -> None:
        candidate = base_candidate(match_status_home="auto_fuzzy_high")
        flags = assess_risk_flags(candidate)

        evaluated, reject_reason, blocked = evaluate_pick_candidate_with_details(candidate)

        self.assertIn("MATCH_FUZZY", flags)
        self.assertEqual(safety_gate_flags(flags), ["MATCH_FUZZY"])
        self.assertIsNone(evaluated)
        self.assertEqual(reject_reason, "safety_gate_blocked")
        self.assertIsNotNone(blocked)
        assert blocked is not None
        self.assertEqual(blocked["pick_safety_status"], "blocked")
        self.assertEqual(blocked["candidate_stage"], "blocked_unsafe_candidate")
        self.assertEqual(blocked["decision_policy_status"], "blocked_by_risk_policy")
        self.assertEqual(blocked["confidence_score_type"], "heuristic_operational")
        self.assertEqual(blocked["pricing_signal_type"], "model_derived_not_calibrated")

    def test_confidence_score_is_traceable_operational_heuristic(self) -> None:
        evaluated, reject_reason, rejected = evaluate_pick_candidate_with_details(base_candidate())

        self.assertIsNone(reject_reason)
        self.assertIsNone(rejected)
        assert evaluated is not None
        self.assertEqual(evaluated["confidence_score"], 5)
        self.assertEqual(evaluated["confidence_score_type"], "heuristic_operational")
        self.assertEqual(evaluated["confidence_score_scale"], "0-5")
        self.assertEqual(evaluated["pricing_signal_type"], "model_derived_not_calibrated")
        self.assertIn("EDGE_FORTE", evaluated["entry_reason"])

    def test_line_selection_rejection_is_traceable_and_not_a_risk_block(self) -> None:
        first = {
            **base_candidate(selection_raw="Mais de 2.5", line=2.5),
            "bet_id": "first",
            "ev_percent": 20.0,
            "confidence_score": 5,
            "stake_units": 1.0,
            "risk_flags": "SEM_FLAG",
            "candidate_stage": "eligible_pick",
            "market_priority": 1,
        }
        second = {
            **base_candidate(selection_raw="Mais de 3.0", line=3.0, odd_entrada=2.1, ev_decimal=0.18),
            "bet_id": "second",
            "ev_percent": 18.0,
            "confidence_score": 5,
            "stake_units": 1.0,
            "risk_flags": "SEM_FLAG",
            "candidate_stage": "eligible_pick",
            "market_priority": 1,
        }

        selected, rejected = select_top_picks(pd.DataFrame([first, second]), return_meta=True)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.iloc[0]["selection_policy_status"], "selected")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["candidate_stage"], "selection_rejected_candidate")
        self.assertEqual(rejected.iloc[0]["selection_policy_status"], "rejected_by_line_selector")
        self.assertEqual(rejected.iloc[0]["portfolio_reject_reason"], "HIGH_CORRELATION_WITH_SELECTED")
        self.assertEqual(rejected.iloc[0].get("pick_safety_status", ""), "")

    def test_selection_core_accepts_plain_candidate_dicts(self) -> None:
        first = {
            **base_candidate(selection_raw="Mais de 2.5", line=2.5),
            "bet_id": "first",
            "ev_percent": 20.0,
            "confidence_score": 5,
            "stake_units": 1.0,
            "risk_flags": "SEM_FLAG",
            "candidate_stage": "eligible_pick",
            "market_priority": 1,
        }
        second = {
            **base_candidate(selection_raw="Mais de 3.0", line=3.0, odd_entrada=2.1, ev_decimal=0.18),
            "bet_id": "second",
            "ev_percent": 18.0,
            "confidence_score": 5,
            "stake_units": 1.0,
            "risk_flags": "SEM_FLAG",
            "candidate_stage": "eligible_pick",
            "market_priority": 1,
        }

        selected, rejected = select_top_candidate_dicts([first, second], return_meta=True)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["bet_id"], "first")
        self.assertEqual(selected[0]["selection_policy_status"], "selected")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["portfolio_reject_reason"], "HIGH_CORRELATION_WITH_SELECTED")

    def test_downstream_payload_loads_decision_and_selection_fields(self) -> None:
        row = {
            **base_candidate(),
            "bet_id": "bet_test",
            "created_at": "2026-04-24 12:00:00",
            "ev_percent": 20.0,
            "pricing_signal_type": "model_derived_not_calibrated",
            "confidence_score": 5,
            "confidence_score_type": "heuristic_operational",
            "confidence_score_scale": "0-5",
            "stake_units": 1.0,
            "pick_safety_status": "safe",
            "candidate_stage": "official_accepted_pick",
            "decision_policy_status": "eligible",
            "selection_policy_status": "selected",
            "safety_gate_reason": "",
            "final_bet_status": "open",
            "final_settlement_status": "pending",
            "risk_flags": "SEM_FLAG",
        }

        payload = build_dashboard_payload(pd.DataFrame([row]), entries_limit=10)

        self.assertEqual(payload["entries"][0]["decision_policy_status"], "eligible")
        self.assertEqual(payload["entries"][0]["selection_policy_status"], "selected")
        self.assertEqual(payload["entries"][0]["confidence_score_type"], "heuristic_operational")
        self.assertEqual(payload["entries"][0]["pricing_signal_type"], "model_derived_not_calibrated")


if __name__ == "__main__":
    unittest.main()
