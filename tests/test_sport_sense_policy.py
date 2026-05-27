from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.sport_sense_policy import apply_sport_sense_policy
from vcbet.core.strategy_config import DEFAULT_CONFIG_PAYLOAD, configure_runtime, get_runtime_config


def _pick(**overrides):
    base = {
        "league": "Liga Test",
        "match_datetime": "2026-05-01 15:00",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "match_name": "Home FC - Away FC",
        "market_scope": "full_time",
        "market_type": "asian_handicap",
        "selection_raw": "Home FC",
        "side": "home",
        "line": 0.0,
        "target_team_role": "home",
        "target_team_name": "Home FC",
        "odd_entrada": 1.80,
        "ev_decimal": 0.12,
        "stake_units": 1.0,
        "lambda_home": 2.0,
        "lambda_away": 1.0,
        "risk_flags": "SEM_FLAG",
    }
    base.update(overrides)
    return base


class SportSensePolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        configure_runtime(config_name="profile_standard")

    def tearDown(self) -> None:
        configure_runtime()

    def test_btts_no_blocked_when_profile_allows_only_yes(self) -> None:
        result = apply_sport_sense_policy(
            _pick(market_type="btts", side="não", selection_raw="Ambas marcam Não"),
            get_runtime_config(),
        )

        self.assertEqual(result["sport_sense_status"], "blocked")
        self.assertEqual(result["sport_sense_reason"], "BTTS_SIDE_BLOCKED")

    def test_odd_inside_blocked_range_is_blocked(self) -> None:
        result = apply_sport_sense_policy(_pick(odd_entrada=2.20), get_runtime_config())

        self.assertEqual(result["sport_sense_status"], "blocked")
        self.assertEqual(result["sport_sense_reason"], "ODD_IN_BLOCKED_RANGE")

    def test_odd_above_2_50_is_allowed_but_stake_is_capped(self) -> None:
        result = apply_sport_sense_policy(_pick(odd_entrada=2.60), get_runtime_config())

        self.assertEqual(result["sport_sense_status"], "approved")
        self.assertTrue(result["stake_policy_applied"])
        self.assertEqual(result["original_stake"], 1.0)
        self.assertEqual(result["stake"], 0.5)
        self.assertEqual(result["stake_units"], 0.5)

    def test_underdog_team_total_over_1_5_is_blocked(self) -> None:
        result = apply_sport_sense_policy(
            _pick(
                market_type="team_total",
                side="over",
                line=1.5,
                target_team_role="away",
                target_team_name="Away FC",
                selection_raw="Away FC Mais de 1.5",
            ),
            get_runtime_config(),
        )

        self.assertEqual(result["team_role"], "underdog")
        self.assertEqual(result["sport_sense_status"], "blocked")
        self.assertEqual(result["sport_sense_reason"], "UNDERDOG_OVER_AGGRESSIVE_LINE")

    def test_underdog_team_total_over_0_5_is_approved(self) -> None:
        result = apply_sport_sense_policy(
            _pick(
                market_type="team_total",
                side="over",
                line=0.5,
                target_team_role="away",
                target_team_name="Away FC",
                selection_raw="Away FC Mais de 0.5",
            ),
            get_runtime_config(),
        )

        self.assertEqual(result["team_role"], "underdog")
        self.assertEqual(result["sport_sense_status"], "approved")
        self.assertEqual(result["sport_sense_reason"], "UNDERDOG_OVER_LOW_LINE_OK")

    def test_favorite_team_total_under_3_0_is_marked_push_safe(self) -> None:
        result = apply_sport_sense_policy(
            _pick(
                market_type="team_total",
                side="under",
                line=3.0,
                target_team_role="home",
                target_team_name="Home FC",
                selection_raw="Home FC Menos de 3.0",
            ),
            get_runtime_config(),
        )

        self.assertEqual(result["team_role"], "favorite")
        self.assertEqual(result["sport_sense_status"], "approved")
        self.assertEqual(result["sport_sense_reason"], "FAVORITE_UNDER_PUSH_LINE_OK")

    def test_mercado_time_is_not_globally_blocked_when_semantic_policy_is_enabled(self) -> None:
        payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
        payload["metadata"] = {
            "name": "tmp_mercado_time",
            "label": "tmp_mercado_time",
            "description": "test",
        }
        payload["enabled_markets"] = ["team_total"]
        payload["rules"]["safety_gates"] = {
            "enabled": True,
            "block_flags": ["MERCADO_TIME"],
        }
        payload["sport_sense_policy"] = {
            "enabled": True,
            "team_total_policy": {
                "enabled": True,
                "block_global_mercado_time_flag": True,
                "underdog_over_allow_lines_lte": 0.5,
                "underdog_over_block_lines_gte": 1.5,
                "favorite_under_allow_lines_gte": 2.5,
                "favorite_under_prefer_push_lines": True,
                "favorite_under_block_lines_lte": 1.5,
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "strategy.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            configure_runtime(config_file=path)

        evaluated, reason, rejected = evaluate_pick_candidate_with_details(
            {
                "match_datetime": "2026-05-01 15:00",
                "league": "Liga Test",
                "home_team": "Home FC",
                "away_team": "Away FC",
                "market_type": "team_total",
                "market_scope": "full_time",
                "selection_raw": "Away FC Mais de 0.5",
                "side": "over",
                "line": 0.5,
                "target_team_role": "away",
                "target_team_name": "Away FC",
                "odd_entrada": 1.80,
                "odd_justa": 1.55,
                "ev_decimal": 0.15,
                "mu_total": 2.8,
                "match_status_home": "auto_exact",
                "match_status_away": "auto_exact",
                "xg_fallback_home": False,
                "xg_fallback_away": False,
            }
        )

        self.assertIsNotNone(evaluated)
        self.assertIsNone(reason)
        self.assertIsNone(rejected)
        self.assertNotIn("MERCADO_TIME", evaluated["risk_flags"])

    def test_missing_fields_do_not_crash_and_produce_unknown_role(self) -> None:
        result = apply_sport_sense_policy({}, get_runtime_config())

        self.assertEqual(result["sport_sense_status"], "approved")
        self.assertEqual(result["team_role"], "unknown")
        self.assertEqual(result["team_role_source"], "unknown")


if __name__ == "__main__":
    unittest.main()
