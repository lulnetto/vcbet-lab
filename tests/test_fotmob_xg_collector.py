from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from vcbet.collectors.fotmob_xg_collector import (
    construir_banco_dados,
    parse_fotmob_league_xg,
    parse_leagues_arg,
    _extract_goals_per_match,
    _find_team_row,
)


SAMPLE_FOTMOB_JSON = {
    "details": {"dataProvider": "opta"},
    "table": [
        {
            "data": {
                "table": {
                    "xg": [
                        {
                            "teamId": 101,
                            "teamName": "Flamengo",
                            "played": 10,
                            "xg": 18.5,
                            "xgConceded": 11.2,
                            "xPoints": 22.0,
                        },
                        {
                            "teamId": 102,
                            "teamName": "Palmeiras",
                            "played": 10,
                            "xg": 16.0,
                            "xgConceded": 10.0,
                            "xPoints": 20.0,
                        },
                        {
                            "teamId": 103,
                            "teamName": "Team Zero",
                            "played": 0,
                            "xg": 5.0,
                            "xgConceded": 3.0,
                            "xPoints": 0.0,
                        },
                        {
                            "teamId": 104,
                            "teamName": "Team NoXg",
                            "played": 10,
                            "xg": None,
                            "xgConceded": 10.0,
                            "xPoints": 0.0,
                        },
                    ],
                    "home": [
                        {"teamId": 101, "scoresStr": "8-5"},
                        {"teamId": 102, "scoresStr": "7-4"},
                    ],
                    "away": [
                        {"teamId": 101, "scoresStr": "7-4"},
                        {"teamId": 102, "scoresStr": "6-3"},
                    ],
                }
            }
        }
    ],
}


class FotMobParsingTest(unittest.TestCase):
    def test_parse_leagues_arg(self) -> None:
        self.assertIsNone(parse_leagues_arg(None))
        self.assertIsNone(parse_leagues_arg(""))
        self.assertEqual(parse_leagues_arg("A, B, C"), ["A", "B", "C"])

    def test_parse_fotmob_league_xg_converts_to_per_match(self) -> None:
        df = parse_fotmob_league_xg(
            league_name="Brasileirão",
            league_id=268,
            ccode3="BRA",
            json_data=SAMPLE_FOTMOB_JSON,
            run_id="run_test",
            collected_at="2026-04-24 12:00:00",
        )

        self.assertEqual(len(df), 2)  # Team Zero and Team NoXg skipped
        self.assertIn("team_name", df.columns)
        self.assertIn("xg", df.columns)
        self.assertIn("xga", df.columns)
        self.assertIn("xg_home", df.columns)
        self.assertIn("xg_away", df.columns)
        self.assertIn("xga_home", df.columns)
        self.assertIn("xga_away", df.columns)

        flamengo = df[df["team_name"] == "Flamengo"].iloc[0]
        self.assertAlmostEqual(flamengo["xg"], 1.85)
        self.assertAlmostEqual(flamengo["xga"], 1.12)
        self.assertAlmostEqual(flamengo["xg_home"], 1.85)
        self.assertAlmostEqual(flamengo["xg_away"], 1.85)
        self.assertAlmostEqual(flamengo["xga_home"], 1.12)
        self.assertAlmostEqual(flamengo["xga_away"], 1.12)
        self.assertEqual(flamengo["xg_split_method"], "fotmob_global_duplicated")
        self.assertEqual(flamengo["source"], "fotmob")
        self.assertEqual(flamengo["source_data_provider"], "opta")
        self.assertEqual(flamengo["fotmob_league_id"], 268)
        self.assertEqual(flamengo["fotmob_ccode3"], "BRA")
        self.assertEqual(flamengo["xg_raw_total"], 18.5)
        self.assertEqual(flamengo["xga_raw_total"], 11.2)

    def test_parse_fotmob_league_xg_missing_table_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_fotmob_league_xg(
                league_name="Test",
                league_id=1,
                ccode3="TST",
                json_data={},
                run_id="run_test",
                collected_at="2026-04-24",
            )
        self.assertIn("missing_table", str(ctx.exception))

    def test_parse_fotmob_league_xg_missing_xg_table_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_fotmob_league_xg(
                league_name="Test",
                league_id=1,
                ccode3="TST",
                json_data={"table": [{"data": {"table": {}}}]},
                run_id="run_test",
                collected_at="2026-04-24",
            )
        self.assertIn("missing_xg_table", str(ctx.exception))

    def test_xg_home_equals_xg_and_xg_away(self) -> None:
        df = parse_fotmob_league_xg(
            league_name="Brasileirão",
            league_id=268,
            ccode3="BRA",
            json_data=SAMPLE_FOTMOB_JSON,
            run_id="run_test",
            collected_at="2026-04-24 12:00:00",
        )
        for _, row in df.iterrows():
            self.assertEqual(row["xg_home"], row["xg"])
            self.assertEqual(row["xg_away"], row["xg"])
            self.assertEqual(row["xga_home"], row["xga"])
            self.assertEqual(row["xga_away"], row["xga"])

    def test_find_team_row(self) -> None:
        table = [{"teamId": 1, "name": "A"}, {"teamId": 2, "name": "B"}]
        self.assertEqual(_find_team_row(table, 1), {"teamId": 1, "name": "A"})
        self.assertEqual(_find_team_row(table, 2), {"teamId": 2, "name": "B"})
        self.assertIsNone(_find_team_row(table, 99))

    def test_extract_goals_per_match(self) -> None:
        home = {"scoresStr": "8-5"}
        away = {"scoresStr": "7-4"}
        result = _extract_goals_per_match(home, away, 10)
        self.assertAlmostEqual(result["goals_for_per_match"], 1.5)
        self.assertAlmostEqual(result["goals_against_per_match"], 0.9)


class FotMobCollectorRunTest(unittest.TestCase):
    def test_collector_creates_snapshot_with_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_fotmob_test"
            target_date = "2026-04-24"

            mock_result = MagicMock(
                ok=True,
                status_code=200,
                json_data=SAMPLE_FOTMOB_JSON,
                error=None,
            )

            with patch(
                "vcbet.collectors.fotmob_xg_collector.FotMobClient.fetch_league_data",
                return_value=mock_result,
            ):
                with patch(
                    "vcbet.collectors.fotmob_xg_collector.carregar_ligas_fotmob"
                ) as mock_ligas:
                    mock_ligas.return_value = {
                        "Brasileirão Série A": {
                            "fotmob_league_id": 268,
                            "fotmob_ccode3": "BRA",
                        }
                    }
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertTrue(snapshot_path.exists())
            df = pd.read_csv(snapshot_path, sep=";")
            required = {
                "run_id",
                "collected_at",
                "source",
                "league",
                "team_name",
                "xg",
                "xga",
                "xg_home",
                "xg_away",
                "xga_home",
                "xga_away",
            }
            self.assertTrue(required.issubset(set(df.columns)))
            self.assertEqual(len(df), 2)
            self.assertTrue((df["source"] == "fotmob").all())
            self.assertTrue((df["xg_split_method"] == "fotmob_global_duplicated").all())

    def test_debug_mode_does_not_write_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_fotmob_debug"
            target_date = "2026-04-24"

            mock_result = MagicMock(
                ok=True,
                status_code=200,
                json_data=SAMPLE_FOTMOB_JSON,
                error=None,
            )

            with patch(
                "vcbet.collectors.fotmob_xg_collector.FotMobClient.fetch_league_data",
                return_value=mock_result,
            ):
                with patch(
                    "vcbet.collectors.fotmob_xg_collector.carregar_ligas_fotmob"
                ) as mock_ligas:
                    mock_ligas.return_value = {
                        "Brasileirão Série A": {
                            "fotmob_league_id": 268,
                            "fotmob_ccode3": "BRA",
                        }
                    }
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=True,
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())

    def test_no_configured_fotmob_leagues_produces_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_fotmob_empty"
            target_date = "2026-04-24"

            with patch(
                "vcbet.collectors.fotmob_xg_collector.carregar_ligas_fotmob"
            ) as mock_ligas:
                mock_ligas.return_value = {}
                construir_banco_dados(
                    run_id=run_id,
                    target_date=target_date,
                    output_dir=output_dir,
                    ligas_alvo=None,
                    modo_debug=False,
                )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())

    def test_fetch_failure_produces_no_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_fotmob_fail"
            target_date = "2026-04-24"

            mock_result = MagicMock(
                ok=False,
                status_code=403,
                json_data=None,
                error="HTTP 403",
            )

            with patch(
                "vcbet.collectors.fotmob_xg_collector.FotMobClient.fetch_league_data",
                return_value=mock_result,
            ):
                with patch(
                    "vcbet.collectors.fotmob_xg_collector.carregar_ligas_fotmob"
                ) as mock_ligas:
                    mock_ligas.return_value = {
                        "Brasileirão Série A": {
                            "fotmob_league_id": 268,
                            "fotmob_ccode3": "BRA",
                        }
                    }
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())


if __name__ == "__main__":
    unittest.main()
