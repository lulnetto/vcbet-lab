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
    extract_mls_supporters_shield_xg_table,
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


MLS_FOTMOB_JSON = {
    "details": {"id": 130, "dataProvider": "enet"},
    "table": [
        {
            "data": {
                "composite": True,
                "leagueId": 130,
                "leagueName": "MLS",
                "tables": [
                    {
                        "leagueName": "Eastern",
                        "table": {
                            "xg": [
                                {
                                    "teamId": 722265,
                                    "teamName": "FC Cincinnati",
                                    "played": 10,
                                    "scoresStr": "19-23",
                                    "xg": 18.735899925231934,
                                    "xgConceded": 14.536900103092194,
                                    "xPoints": 16.27643687327153,
                                }
                            ]
                        },
                    },
                    {
                        "leagueName": "Western",
                        "table": {
                            "xg": [
                                {
                                    "teamId": 307691,
                                    "teamName": "Vancouver Whitecaps",
                                    "played": 9,
                                    "scoresStr": "25-5",
                                    "xg": 25.90910017490387,
                                    "xgConceded": 6.216799974441528,
                                    "xPoints": 23.64037839251569,
                                }
                            ]
                        },
                    },
                    {
                        "leagueName": "Supporters Shield",
                        "table": {
                            "all": [
                                {
                                    "name": "San Jose Earthquakes",
                                    "shortName": "San Jose",
                                    "id": 6603,
                                    "played": 10,
                                    "scoresStr": "25-6",
                                }
                            ],
                            "home": [
                                {
                                    "name": "Vancouver Whitecaps",
                                    "shortName": "Vancouver",
                                    "id": 307691,
                                    "played": 8,
                                    "scoresStr": "21-4",
                                    "goalsScored": 21,
                                }
                            ],
                            "away": [
                                {
                                    "name": "Inter Miami CF",
                                    "shortName": "Inter Miami CF",
                                    "id": 960720,
                                    "played": 7,
                                    "scoresStr": "14-10",
                                    "goalsScored": 14,
                                }
                            ],
                            "xg": [
                                {
                                    "name": "Vancouver Whitecaps",
                                    "shortName": "Vancouver",
                                    "id": 307691,
                                    "teamId": 307691,
                                    "teamName": "Vancouver Whitecaps",
                                    "played": 9,
                                    "scoresStr": "25-5",
                                    "xg": 25.90910017490387,
                                    "xgConceded": 6.216799974441528,
                                    "xPoints": 23.64037839251569,
                                },
                                {
                                    "name": "San Jose Earthquakes",
                                    "shortName": "San Jose",
                                    "id": 6603,
                                    "teamId": 6603,
                                    "teamName": "San Jose Earthquakes",
                                    "played": 10,
                                    "scoresStr": "25-6",
                                    "xg": 30.5,
                                    "xgConceded": 12.3,
                                    "xPoints": 25.0,
                                },
                            ],
                        },
                    },
                ]
            }
        }
    ],
}


class MlsFotMobParsingTest(unittest.TestCase):
    def test_extract_mls_supporters_shield_returns_inner_table(self) -> None:
        inner = extract_mls_supporters_shield_xg_table(MLS_FOTMOB_JSON)
        self.assertIn("xg", inner)
        self.assertEqual(len(inner["xg"]), 2)
        names = {row["name"] for row in inner["xg"]}
        self.assertEqual(names, {"Vancouver Whitecaps", "San Jose Earthquakes"})

    def test_parse_mls_chooses_supporters_shield(self) -> None:
        df = parse_fotmob_league_xg(
            league_name="MLS",
            league_id=130,
            ccode3="USA",
            json_data=MLS_FOTMOB_JSON,
            run_id="run_test",
            collected_at="2026-04-28 20:00:00",
        )
        self.assertEqual(len(df), 2)
        names = set(df["team_name"].tolist())
        self.assertEqual(names, {"Vancouver Whitecaps", "San Jose Earthquakes"})
        vancouver = df[df["team_name"] == "Vancouver Whitecaps"].iloc[0]
        self.assertEqual(vancouver["source_team_id"], 307691)
        self.assertAlmostEqual(vancouver["xg_raw_total"], 25.90910017490387, places=4)
        self.assertAlmostEqual(vancouver["xga_raw_total"], 6.216799974441528, places=4)
        self.assertAlmostEqual(vancouver["xpoints"], 23.64037839251569, places=4)

    def test_parse_mls_scores_goals_per_match(self) -> None:
        df = parse_fotmob_league_xg(
            league_name="MLS",
            league_id=130,
            ccode3="USA",
            json_data=MLS_FOTMOB_JSON,
            run_id="run_test",
            collected_at="2026-04-28 20:00:00",
        )
        vancouver = df[df["team_name"] == "Vancouver Whitecaps"].iloc[0]
        # home scoresStr "21-4" + away not present for Vancouver in sample
        # but home row exists, away row does not -> goals_for = 21, goals_against = 4
        self.assertAlmostEqual(vancouver["goals_home_per_match"], 21.0 / 9)
        # away row is None for Vancouver in the sample because away table has Inter Miami
        self.assertIsNone(vancouver["goals_away_per_match"])
        self.assertAlmostEqual(vancouver["goals_for_per_match"], 21.0 / 9)
        self.assertAlmostEqual(vancouver["goals_against_per_match"], 4.0 / 9)

    def test_no_confusion_with_external_league_name(self) -> None:
        # Even though outer leagueName is "MLS", we must NOT look for "Supporters Shield"
        # at the outer level. The function should fail if tables key is missing.
        bad_payload = {
            "details": {"id": 130},
            "table": [{"data": {"leagueName": "MLS"}}],
        }
        with self.assertRaises(ValueError) as ctx:
            extract_mls_supporters_shield_xg_table(bad_payload)
        self.assertIn("missing_mls_supporters_shield", str(ctx.exception))


class UnifiedCollectorFallbackTest(unittest.TestCase):
    def test_fallback_fotmob_fails_then_footystats_succeeds(self) -> None:
        from vcbet.collectors.xg_daily_store import construir_banco_dados_unificado

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "vcbet.collectors.xg_daily_store.carregar_ligas_fotmob"
            ) as mock_fotmob_map, patch(
                "vcbet.collectors.xg_daily_store.carregar_ligas_footystats"
            ) as mock_fs_map, patch(
                "vcbet.collectors.xg_daily_store.FotMobClient"
            ) as MockClient, patch(
                "vcbet.collectors.xg_daily_store._fetch_html_requests"
            ) as mock_fetch:

                mock_fotmob_map.return_value = {"Test League": {"fotmob_league_id": 999, "fotmob_ccode3": "TST"}}
                mock_fs_map.return_value = {"Test League": "https://footystats.org/test/league"}

                # FotMob fails
                mock_client = MagicMock()
                mock_client.warmup.return_value = MagicMock(ok=True)
                mock_client.fetch_league_data.return_value = MagicMock(
                    ok=False, status_code=403, json_data=None, error="HTTP 403"
                )
                MockClient.return_value = mock_client

                # FootyStats succeeds
                mock_fetch.return_value = (
                    "<html><table class='full-league-table'>"
                    "<thead><th>Team</th><th>XG</th><th>XGA</th></thead>"
                    "<tbody>"
                    "<tr><td class='team'><a>Team A</a></td><td>1.5</td><td>1.2</td></tr>"
                    "</tbody></table></html>"
                )

                construir_banco_dados_unificado(
                    run_id="run_unified",
                    target_date="2026-04-28",
                    output_dir=tmp,
                    ligas_alvo=["Test League"],
                )

            snapshot_path = Path(tmp) / "2026-04-28" / "run_unified" / "xg_snapshot.csv"
            self.assertTrue(snapshot_path.exists())
            df = pd.read_csv(snapshot_path, sep=";")
            self.assertEqual(len(df), 1)
            self.assertEqual(df.iloc[0]["source"], "footystats")
            self.assertEqual(df.iloc[0]["league"], "Test League")

    def test_league_skipped_when_both_sources_fail(self) -> None:
        from vcbet.collectors.xg_daily_store import construir_banco_dados_unificado

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "vcbet.collectors.xg_daily_store.carregar_ligas_fotmob"
            ) as mock_fotmob_map, patch(
                "vcbet.collectors.xg_daily_store.carregar_ligas_footystats"
            ) as mock_fs_map, patch(
                "vcbet.collectors.xg_daily_store.FotMobClient"
            ) as MockClient, patch(
                "vcbet.collectors.xg_daily_store._fetch_html_requests"
            ) as mock_fetch:

                mock_fotmob_map.return_value = {"Bad League": {"fotmob_league_id": 998, "fotmob_ccode3": "BAD"}}
                mock_fs_map.return_value = {"Bad League": "https://footystats.org/bad/league"}

                mock_client = MagicMock()
                mock_client.warmup.return_value = MagicMock(ok=True)
                mock_client.fetch_league_data.return_value = MagicMock(
                    ok=False, status_code=500, json_data=None, error="HTTP 500"
                )
                MockClient.return_value = mock_client

                mock_fetch.side_effect = RuntimeError("Blocked")

                construir_banco_dados_unificado(
                    run_id="run_skip",
                    target_date="2026-04-28",
                    output_dir=tmp,
                    ligas_alvo=["Bad League"],
                )

            snapshot_path = Path(tmp) / "2026-04-28" / "run_skip" / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())

    def test_xg_daily_store_respects_output_dir(self) -> None:
        from vcbet.collectors.xg_daily_store import get_or_build_daily_xg

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "vcbet.collectors.xg_daily_store.carregar_ligas_fotmob"
            ) as mock_fotmob_map, patch(
                "vcbet.collectors.xg_daily_store.FotMobClient"
            ) as MockClient:

                mock_fotmob_map.return_value = {"Brasileirão Série A": {"fotmob_league_id": 268, "fotmob_ccode3": "BRA"}}
                mock_client = MagicMock()
                mock_client.warmup.return_value = MagicMock(ok=True)
                mock_client.fetch_league_data.return_value = MagicMock(
                    ok=True, status_code=200, json_data=SAMPLE_FOTMOB_JSON, error=None
                )
                MockClient.return_value = mock_client

                path = get_or_build_daily_xg(
                    target_date="2026-04-28",
                    source="fotmob",
                    leagues="Brasileirão Série A",
                    output_dir=tmp,
                    snapshot_date="2026-04-28",
                )
                self.assertTrue(Path(path).exists())
                self.assertTrue(str(path).startswith(str(tmp)))


class PipelineSkipMissingXgTest(unittest.TestCase):
    def test_leagues_without_xg_skipped_before_pricing(self) -> None:
        from vcbet.core.pipeline.filtering_stage import build_normalization_filter

        df_betano = pd.DataFrame({
            "league": ["Premier League", "Premier League", "MLS", "MLS"],
            "normalized_status": ["ok", "ok", "ok", "ok"],
            "market_scope": ["full_time", "full_time", "full_time", "full_time"],
            "market_type": ["total_goals", "btts", "total_goals", "btts"],
            "home_team": ["Arsenal", "Chelsea", "LAFC", "Inter Miami"],
            "away_team": ["Liverpool", "Man City", "LA Galaxy", "Orlando"],
            "match_name": ["Arsenal - Liverpool", "Chelsea - Man City", "LAFC - LA Galaxy", "Inter Miami - Orlando"],
            "selection_raw": ["Over 2.5", "Sim", "Over 2.5", "Sim"],
            "odd": [2.0, 1.8, 2.1, 1.9],
        })

        df_xg = pd.DataFrame({
            "league": ["Premier League", "Premier League"],
            "team_name": ["Arsenal", "Liverpool"],
            "xg": [1.8, 1.9],
            "xga": [1.2, 1.1],
            "xg_home": [1.8, 1.9],
            "xg_away": [1.8, 1.9],
            "xga_home": [1.2, 1.1],
            "xga_away": [1.2, 1.1],
        })

        result = build_normalization_filter(df_betano, df_xg, {"total_goals", "btts"})
        df_alvo = result["df_alvo"]
        skipped = result.get("league_skipped_missing_xg_snapshot", {})

        self.assertEqual(len(df_alvo), 2)
        self.assertTrue((df_alvo["league"] == "Premier League").all())
        self.assertEqual(skipped.get("MLS"), 2)


if __name__ == "__main__":
    unittest.main()
