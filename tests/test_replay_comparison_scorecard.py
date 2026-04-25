from __future__ import annotations

import unittest

from vcbet.replay.replay_pipeline import (
    MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
    MANUAL_DEFAULT_BASELINE_CONFIG,
    _build_comparison_context,
    _build_config_scorecard,
)


class ReplayComparisonScorecardTest(unittest.TestCase):
    def test_config_scorecard_exposes_replay_evidence_coherently(self) -> None:
        item = {
            "config_name": MANUAL_DEFAULT_BASELINE_CONFIG,
            "return_code": 0,
            "picks_total": 3,
            "picks_by_market": {"asian_total": 2, "total_goals": 1},
            "picks_by_league": {"Liga A": 2, "Liga B": 1},
            "comparison": {
                "reference_total": 4,
                "candidate_total": 3,
                "overlap": 2,
                "precision": 66.67,
                "recall": 50.0,
                "jaccard": 40.0,
            },
            "asian_total_line_drift": {"shifted_line_matches_total": 1},
            "quality_processing": {
                "discard_reason_counts": {
                    "pick_filter_edge_below_min": 5,
                    "pick_filter_odd_out_of_range": 2,
                }
            },
            "settlement": {
                "settlement_summary": {
                    "settled": 2,
                    "open": 1,
                    "wins": 1,
                    "losses": 1,
                    "pushes": 0,
                    "model_units": 0.35,
                    "model_roi_percent": 23.33,
                }
            },
        }

        scorecard = _build_config_scorecard(item)

        self.assertEqual(scorecard["config_name"], MANUAL_DEFAULT_BASELINE_CONFIG)
        self.assertEqual(scorecard["role"], "default_baseline")
        self.assertEqual(scorecard["role_source"], "manual_policy")
        self.assertTrue(scorecard["is_default_baseline"])
        self.assertFalse(scorecard["is_conservative_reference"])
        self.assertEqual(scorecard["primary_candidate_status"], "primary")
        self.assertEqual(scorecard["picks_total"], 3)
        self.assertEqual(scorecard["source_picks_total"], 4)
        self.assertEqual(scorecard["overlap_with_source"], 2)
        self.assertEqual(scorecard["precision_percent"], 66.67)
        self.assertEqual(scorecard["recall_percent"], 50.0)
        self.assertEqual(scorecard["jaccard_percent"], 40.0)
        self.assertEqual(scorecard["picks_by_market"]["asian_total"], 2)
        self.assertEqual(scorecard["picks_by_league"]["Liga A"], 2)
        self.assertEqual(scorecard["asian_total_shifted_lines"], 1)
        self.assertEqual(scorecard["quality_discards"]["edge_below_min"], 5)
        self.assertEqual(scorecard["quality_discards"]["odd_out_of_range"], 2)
        self.assertEqual(scorecard["model_result_summary"]["settled"], 2)
        self.assertEqual(scorecard["model_result_summary"]["model_units"], 0.35)
        self.assertIn("not proof", scorecard["evidence_note"])

    def test_comparison_context_identifies_baseline_reference_and_non_primary_configs(self) -> None:
        scorecards = [
            _build_config_scorecard({"config_name": MANUAL_DEFAULT_BASELINE_CONFIG, "comparison": {}}),
            _build_config_scorecard({"config_name": MANUAL_CONSERVATIVE_REFERENCE_CONFIG, "comparison": {}}),
            _build_config_scorecard({"config_name": "intermediate_balanced", "comparison": {}}),
            _build_config_scorecard({"config_name": "legacy_recovered", "comparison": {}}),
        ]

        context = _build_comparison_context(scorecards)

        self.assertEqual(context["default_baseline_config"], MANUAL_DEFAULT_BASELINE_CONFIG)
        self.assertEqual(context["conservative_reference_config"], MANUAL_CONSERVATIVE_REFERENCE_CONFIG)
        self.assertEqual(context["recommendation_method"], "manual_policy")
        self.assertFalse(context["metric_ranking_applied"])
        self.assertIn("manual policy", context["recommendation_basis"])
        self.assertEqual(context["secondary_candidate_configs"], ["intermediate_balanced"])
        self.assertEqual(context["deprecated_reference_configs"], ["legacy_recovered"])
        self.assertIn("not proof", context["profitability_caveat"])
        self.assertIn("metric-ranked", context["profitability_caveat"])

    def test_scorecard_keeps_existing_comparison_payload_compatible(self) -> None:
        item = {
            "config_name": "custom_config",
            "picks_total": 0,
            "comparison": {
                "reference_total": 0,
                "candidate_total": 0,
                "overlap": 0,
                "precision": 0.0,
                "recall": 0.0,
                "jaccard": 0.0,
                "missing_from_candidate": [],
                "extra_in_candidate": [],
            },
        }

        scorecard = _build_config_scorecard(item)

        self.assertEqual(item["comparison"]["missing_from_candidate"], [])
        self.assertEqual(item["comparison"]["extra_in_candidate"], [])
        self.assertEqual(scorecard["role"], "secondary_candidate")
        self.assertEqual(scorecard["model_result_summary"]["available"], False)


if __name__ == "__main__":
    unittest.main()
