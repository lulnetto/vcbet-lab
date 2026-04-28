from __future__ import annotations

import unittest

import pandas as pd

from vcbet.core.data_health import validate_snapshot_health


class DataHealthTest(unittest.TestCase):
    def test_empty_odds_fails(self) -> None:
        result = validate_snapshot_health(
            pd.DataFrame(), pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0]})
        )
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("empty_odds_snapshot", codes)

    def test_empty_xg_fails(self) -> None:
        result = validate_snapshot_health(
            pd.DataFrame({"league": ["L1"], "match_name": ["A - B"], "home_team": ["A"], "away_team": ["B"], "market_type": ["total_goals"], "market_scope": ["full_time"], "odd": [2.0], "selection_raw": ["over"]}),
            pd.DataFrame(),
        )
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("empty_xg_snapshot", codes)

    def test_critical_invalid_rate_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1", "L1", "L1"],
            "match_name": ["A - B", "C - D", "E - F"],
            "home_team": ["A", "C", "E"],
            "away_team": ["B", "D", "F"],
            "market_type": ["total_goals", "total_goals", "total_goals"],
            "market_scope": ["full_time", "full_time", "full_time"],
            "odd": [2.0, -1.0, 0.0],
            "selection_raw": ["over", "under", "over"],
            "normalized_status": ["ok", "ok", "ok"],
            "run_id": ["r1", "r1", "r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        result = validate_snapshot_health(df_odds, df_xg, max_critical_invalid_rate=0.25)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_critical_invalid_rate_high", codes)

    def test_valid_minimal_fixture_passes(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A", "B"], "league": ["L1", "L1"], "xg": [1.0, 0.8], "run_id": ["r1", "r1"]})
        result = validate_snapshot_health(df_odds, df_xg)
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["errors"], [])

    def test_no_eligible_markets_is_warning_not_fatal(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["error"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        result = validate_snapshot_health(df_odds, df_xg)
        self.assertTrue(result["is_valid"])
        error_codes = [e["code"] for e in result["errors"]]
        self.assertNotIn("no_eligible_markets", error_codes)
        warning_codes = [w["code"] for w in result["warnings"]]
        self.assertIn("no_eligible_markets", warning_codes)

    def test_missing_provenance_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0]})
        result = validate_snapshot_health(df_odds, df_xg)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_missing_provenance", codes)
        self.assertIn("xg_missing_provenance", codes)

    def test_manifest_partial_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        manifest = {"status": "partial", "totals": {}}
        result = validate_snapshot_health(df_odds, df_xg, odds_manifest=manifest)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_manifest_status_bad", codes)

    def test_manifest_failed_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        manifest = {"status": "failed", "totals": {}}
        result = validate_snapshot_health(df_odds, df_xg, odds_manifest=manifest)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_manifest_status_bad", codes)

    def test_high_unsupported_market_rate_does_not_fatal_when_manifest_healthy(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1", "L1", "L1"],
            "match_name": ["A - B", "C - D", "E - F"],
            "home_team": ["A", "C", "E"],
            "away_team": ["B", "D", "F"],
            "market_type": ["total_goals", "total_goals", "total_goals"],
            "market_scope": ["full_time", "full_time", "full_time"],
            "odd": [2.0, 2.1, 2.2],
            "selection_raw": ["over", "under", "over"],
            "normalized_status": ["ok", "unknown_market", "unknown_market"],
            "run_id": ["r1", "r1", "r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        manifest = {
            "status": "completed",
            "totals": {
                "events_found": 2,
                "events_success": 2,
                "events_failed": 0,
                "raw_selections_seen": 50,
                "normalized_ok_rows": 1,
            }
        }
        result = validate_snapshot_health(df_odds, df_xg, odds_manifest=manifest)
        self.assertTrue(result["is_valid"])
        warning_codes = [w["code"] for w in result["warnings"]]
        self.assertIn("unsupported_market_rate_high", warning_codes)

    def test_manifest_event_failure_rate_high_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        manifest = {
            "status": "completed",
            "totals": {
                "events_found": 4,
                "events_success": 1,
                "events_failed": 3,
                "raw_selections_seen": 50,
                "normalized_ok_rows": 5,
            }
        }
        result = validate_snapshot_health(df_odds, df_xg, odds_manifest=manifest, max_event_failure_rate=0.25)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_event_failure_rate_high", codes)

    def test_manifest_avg_raw_selections_low_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        manifest = {
            "status": "completed",
            "totals": {
                "events_found": 2,
                "events_success": 2,
                "events_failed": 0,
                "raw_selections_seen": 10,
                "normalized_ok_rows": 5,
            }
        }
        result = validate_snapshot_health(df_odds, df_xg, odds_manifest=manifest, min_raw_selections_per_event=10)
        # avg raw = 5 -> below 10 -> fatal
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_avg_raw_selections_low", codes)

    def test_invalid_raw_odds_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1", "L1"],
            "match_name": ["A - B", "C - D"],
            "home_team": ["A", "C"],
            "away_team": ["B", "D"],
            "market_type": ["total_goals", "total_goals"],
            "market_scope": ["full_time", "full_time"],
            "odd": [2.0, "invalid"],
            "selection_raw": ["over", "under"],
            "normalized_status": ["ok", "ok"],
            "run_id": ["r1", "r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        result = validate_snapshot_health(df_odds, df_xg, max_critical_invalid_rate=0.25)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_critical_invalid_rate_high", codes)

    def test_missing_structural_fields_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1", "L1"],
            "match_name": ["A - B", ""],
            "home_team": ["A", "C"],
            "away_team": ["B", "D"],
            "market_type": ["total_goals", "total_goals"],
            "market_scope": ["full_time", "full_time"],
            "odd": [2.0, 2.1],
            "selection_raw": ["over", "under"],
            "normalized_status": ["ok", "ok"],
            "run_id": ["r1", "r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        result = validate_snapshot_health(df_odds, df_xg, max_critical_invalid_rate=0.25)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_critical_invalid_rate_high", codes)

    def test_min_odd_filtered_rows_is_warning_not_fatal(self) -> None:
        # Simulate collector manifest where min_odd filtered everything but raw data was healthy
        df_odds = pd.DataFrame({
            "league": ["L1"],
            "match_name": ["A - B"],
            "home_team": ["A"],
            "away_team": ["B"],
            "market_type": ["total_goals"],
            "market_scope": ["full_time"],
            "odd": [2.0],
            "selection_raw": ["over"],
            "normalized_status": ["ok"],
            "run_id": ["r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        manifest = {
            "status": "completed",
            "totals": {
                "events_found": 1,
                "events_success": 1,
                "events_failed": 0,
                "raw_selections_seen": 20,
                "supported_market_rows_before_min_odd": 10,
                "rows_after_min_odd_filter": 0,
                "normalized_ok_rows": 5,
            }
        }
        result = validate_snapshot_health(df_odds, df_xg, odds_manifest=manifest)
        self.assertTrue(result["is_valid"])
        # No fatal error about min_odd; the manifest avg raw = 20 >= 10, normalized_ok = 5 > 0
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
