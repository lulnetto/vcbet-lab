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

    def test_high_failure_rate_fails(self) -> None:
        df_odds = pd.DataFrame({
            "league": ["L1", "L1"],
            "match_name": ["A - B", "C - D"],
            "home_team": ["A", "C"],
            "away_team": ["B", "D"],
            "market_type": ["total_goals", "total_goals"],
            "market_scope": ["full_time", "full_time"],
            "odd": [2.0, 2.1],
            "selection_raw": ["over", "under"],
            "normalized_status": ["ok", "error"],
            "run_id": ["r1", "r1"],
        })
        df_xg = pd.DataFrame({"team_name": ["A"], "league": ["L1"], "xg": [1.0], "run_id": ["r1"]})
        result = validate_snapshot_health(df_odds, df_xg, max_invalid_snapshot_row_rate=0.25)
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("odds_failure_rate_high", codes)

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

    def test_no_eligible_markets_fails(self) -> None:
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
        self.assertFalse(result["is_valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("no_eligible_markets", codes)

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


if __name__ == "__main__":
    unittest.main()
