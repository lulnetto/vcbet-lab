from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vcbet.collectors.odds_collector import (
    BetanoExtractor,
    SUPPORTED_MARKET_TYPE_IDS,
    build_betano_api_odds_url,
    build_odds_manifest,
    evaluate_collection_health,
    extract_initial_state_json,
    save_to_csv,
)
from vcbet.core.pipeline.input_loader import carregar_snapshot_odds


class ExtractInitialStateJsonTest(unittest.TestCase):
    def test_json_followed_by_extra_script(self) -> None:
        html = '''<html><script>window["initial_state"]={"data":{"blocks":[]}};var x=1;</script><body></body></html>'''
        result = extract_initial_state_json(html)
        self.assertEqual(result, {"data": {"blocks": []}})

    def test_escaped_quotes_and_braces_inside_strings(self) -> None:
        state = {"msg": 'He said "hello" and {not} json', "data": {}}
        html = f'<script>window["initial_state"]={json.dumps(state)};</script>'
        result = extract_initial_state_json(html)
        self.assertEqual(result["msg"], 'He said "hello" and {not} json')
        self.assertEqual(result["data"], {})

    def test_missing_marker_returns_empty(self) -> None:
        html = '<html><body>nothing here</body></html>'
        result = extract_initial_state_json(html)
        self.assertEqual(result, {})


class BuildApiUrlTest(unittest.TestCase):
    def test_converts_odds_path_to_api_odds(self) -> None:
        url = build_betano_api_odds_url("/odds/girona-fc-mallorca/80663624/")
        self.assertIn("/api/odds/", url)
        self.assertIn("bt=14", url)

    def test_preserves_full_url(self) -> None:
        url = build_betano_api_odds_url("https://www.betano.bet.br/odds/test/12345/")
        self.assertTrue(url.startswith("https://www.betano.bet.br/api/odds/"))
        self.assertIn("bt=14", url)


class MockJsonResponse:
    def __init__(self, status_code: int, data: dict | None = None, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self._data = data
        self.text = text
        self.headers = headers or {}
        self.url = "https://www.betano.bet.br/api/odds/test/12345/?bt=14"

    def json(self):
        if self._data is None:
            raise json.JSONDecodeError("No data", self.text, 0)
        return self._data


class MockHtmlResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": "text/html"}
        self.url = "https://www.betano.bet.br/odds/test/12345/?bt=14"


class BetanoExtractorFetchTest(unittest.TestCase):
    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_non_2xx_league_page_is_rejected_and_retried(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        responses = [
            MockHtmlResponse(500, "error"),
            MockHtmlResponse(500, "error"),
            MockHtmlResponse(200, 'window["initial_state"]={"data":{"blocks":[]}};'),
        ]
        session.get.side_effect = responses
        urls, diag = extractor.get_match_urls_by_date("/liga/teste", "2026-04-28")
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual(urls, [])
        self.assertTrue(diag["success"])

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_event_api_json_parses_supported_typeids(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        data = {
            "data": {
                "event": {
                    "id": "evt1",
                    "leagueId": "lig1",
                    "name": "Team A - Team B",
                    "startTime": 1714309200000,
                    "marketsCount": 3,
                    "totalMarketsAvailable": 329,
                    "markets": [
                        {
                            "id": "m1",
                            "name": "Total de Gols Mais/Menos",
                            "type": "MRES",
                            "typeId": 13,
                            "selections": [
                                {"id": "s1", "name": "Mais de 2.5", "price": 2.0, "betRef": "b1"}
                            ],
                        },
                        {
                            "id": "m2",
                            "name": "Ambas equipes Marcam",
                            "type": "BTSC",
                            "typeId": 15,
                            "selections": [
                                {"id": "s2", "name": "Sim", "price": 1.8, "betRef": "b2"}
                            ],
                        },
                        {
                            "id": "m3",
                            "name": "Handicap Asiático",
                            "type": "HCTG",
                            "typeId": 185,
                            "selections": [
                                {"id": "s3", "name": "Team A -1.5", "price": 2.2, "betRef": "b3"}
                            ],
                        },
                    ],
                }
            }
        }
        session.get.return_value = MockJsonResponse(200, data, headers={"Content-Type": "application/json"})
        rows, diag = extractor.extract_all_odds("/odds/test/12345/", "Liga", "run1")
        self.assertTrue(diag["success"])
        types = {r["betano_market_type"] for r in rows}
        self.assertIn("MRES", types)
        self.assertIn("BTSC", types)
        self.assertIn("HCTG", types)
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(rows[0]["betano_fetch_method"], "event_api_odds_bt14")

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_event_api_json_fallback_to_html_when_json_fails(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        # API returns non-JSON (blocked HTML page)
        html_state = {
            "data": {
                "event": {
                    "id": "evt1",
                    "leagueId": "lig1",
                    "name": "Team A - Team B",
                    "startTime": 1714309200000,
                    "marketsCount": 2,
                    "totalMarketsAvailable": 200,
                    "markets": [
                        {
                            "id": "m1",
                            "name": "Total de Gols Mais/Menos",
                            "type": "MRES",
                            "typeId": 13,
                            "selections": [
                                {"id": "s1", "name": "Mais de 2.5", "price": 2.0, "betRef": "b1"},
                                {"id": "s2", "name": "Menos de 2.5", "price": 1.9, "betRef": "b2"},
                            ],
                        },
                        {
                            "id": "m2",
                            "name": "Ambas equipes Marcam",
                            "type": "BTSC",
                            "typeId": 15,
                            "selections": [
                                {"id": "s3", "name": "Sim", "price": 1.8, "betRef": "b3"},
                            ],
                        },
                    ],
                }
            }
        }
        html_response = MockHtmlResponse(200, 'window["initial_state"]=' + json.dumps(html_state) + ";")
        api_response = MockHtmlResponse(200, '<html><body>blocked</body></html>')
        session.get.side_effect = [api_response, api_response, api_response, html_response]
        rows, diag = extractor.extract_all_odds("/odds/test/12345/", "Liga", "run1")
        self.assertTrue(diag["success"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["betano_fetch_method"], "event_html_initial_state_bt14_fallback")

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_event_missing_supported_markets_fails(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        data = {
            "data": {
                "event": {
                    "id": "evt1",
                    "leagueId": "lig1",
                    "name": "Team A - Team B",
                    "startTime": 1714309200000,
                    "marketsCount": 5,
                    "totalMarketsAvailable": 329,
                    "markets": [
                        {
                            "id": "m1",
                            "name": "Resultado Final",
                            "type": "MRES",
                            "typeId": 1,
                            "selections": [
                                {"id": "s1", "name": "Team A", "price": 2.0, "betRef": "b1"}
                            ],
                        },
                    ],
                }
            }
        }
        session.get.return_value = MockJsonResponse(200, data, headers={"Content-Type": "application/json"})
        rows, diag = extractor.extract_all_odds("/odds/test/12345/", "Liga", "run1")
        self.assertFalse(diag["success"])
        self.assertEqual(diag["failure_reason"], "event_missing_supported_markets")

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_tablelayout_selections_are_parsed(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        data = {
            "data": {
                "event": {
                    "id": "evt1",
                    "leagueId": "lig1",
                    "name": "Team A - Team B",
                    "startTime": 1714309200000,
                    "marketsCount": 1,
                    "totalMarketsAvailable": 100,
                    "markets": [
                        {
                            "id": "m4",
                            "name": "Total de Gols Mais/Menos",
                            "type": "MRES",
                            "typeId": 13,
                            "tableLayout": {
                                "rows": [
                                    {
                                        "name": "Row1",
                                        "groupSelections": [
                                            {
                                                "name": "Group1",
                                                "selections": [
                                                    {"id": "s4", "name": "Menos de 2.5", "price": 1.9, "betRef": "b4"},
                                                    {"id": "s5", "name": "Mais de 2.5", "price": 2.0, "betRef": "b5"},
                                                ],
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    ],
                }
            }
        }
        session.get.return_value = MockJsonResponse(200, data, headers={"Content-Type": "application/json"})
        rows, diag = extractor.extract_all_odds("/odds/test/12345/", "Liga", "run1")
        self.assertTrue(diag["success"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["betano_table_row_name"], "Row1")
        self.assertEqual(rows[0]["betano_group_name"], "Group1")
        self.assertEqual(rows[0]["betano_selection_id"], "s4")


class CollectorMainBlockTest(unittest.TestCase):
    def _run_collector(self, mock_ligas: list, mock_extract_side_effect: list, extra_args: list | None = None):
        tmpdir = tempfile.mkdtemp()
        run_id = "test_run_001"
        args = [
            "odds_collector.py",
            "--run-id", run_id,
            "--d", "2026-04-28",
            "--output-dir", tmpdir,
        ] + (extra_args or [])
        with patch.object(sys, "argv", args):
            with patch("vcbet.collectors.odds_collector.carregar_ligas_betano", return_value=mock_ligas):
                mock_instance = MagicMock()
                mock_instance.get_match_urls_by_date.return_value = (["/match/1"], {"success": True, "events_found": 1})
                mock_instance.extract_all_odds.side_effect = mock_extract_side_effect
                with patch("vcbet.collectors.odds_collector.BetanoExtractor", return_value=mock_instance):
                    import vcbet.collectors.odds_collector as oc
                    try:
                        oc.main()
                    except SystemExit as exc:
                        return Path(tmpdir) / "2026-04-28" / run_id, exc.code
        return Path(tmpdir) / "2026-04-28" / run_id, None

    def test_collector_does_not_save_snapshot_when_event_failures_exceed_threshold(self) -> None:
        diag = {
            "success": False,
            "raw_markets_seen": 0,
            "raw_selections_seen": 0,
            "supported_market_rows_seen": 0,
            "supported_market_rows_with_valid_odd": 0,
            "normalized_ok_rows": 0,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {},
            "markets_seen_by_type_id": {},
            "failure_reason": "missing_initial_state",
        }
        run_dir, exit_code = self._run_collector(
            mock_ligas=[{"nome": "Liga Test", "path": "/liga/test"}],
            mock_extract_side_effect=[([], diag)],
        )
        self.assertEqual(exit_code, 1)
        self.assertFalse((run_dir / "odds_snapshot.csv").exists())
        manifest_path = run_dir / "odds_collection_manifest.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual(m["status"], "failed")
        self.assertIn("no_events_success", m["failure_reasons"])

    def test_collector_saves_snapshot_for_one_healthy_event_day(self) -> None:
        rows = [
            {
                "run_id": "run1", "collected_at": "2026-04-28 10:00:00", "source": "betano",
                "league": "Liga Test", "match_datetime": "2026-04-28 15:00", "home_team": "A", "away_team": "B",
                "match_name": "A - B", "market_raw": "Total de Gols Mais/Menos", "selection_raw": "Mais de 2.5",
                "odd": 2.0, "event_url": "http://example.com",
                "market_type": "total_goals", "market_scope": "full_time", "side": "over",
                "line": 2.5, "target_team_role": "geral", "target_team_name": "geral", "normalized_status": "ok",
            }
        ]
        diag = {
            "success": True,
            "raw_markets_seen": 5,
            "raw_selections_seen": 20,
            "supported_market_rows_seen": 10,
            "supported_market_rows_with_valid_odd": 5,
            "normalized_ok_rows": 5,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {"Total de Gols Mais/Menos": 1},
            "markets_seen_by_type_id": {13: 1},
            "failure_reason": None,
        }
        run_dir, exit_code = self._run_collector(
            mock_ligas=[{"nome": "Liga Test", "path": "/liga/test"}],
            mock_extract_side_effect=[(rows, diag)],
        )
        self.assertIsNone(exit_code)
        self.assertTrue((run_dir / "odds_snapshot.csv").exists())
        manifest_path = run_dir / "odds_collection_manifest.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual(m["status"], "completed")
        self.assertEqual(m["totals"]["events_found"], 1)
        self.assertEqual(m["totals"]["events_success"], 1)
        self.assertEqual(m["leagues"]["Liga Test"]["events_success"], 1)

    def test_manifest_written_with_totals_and_per_league_diagnostics(self) -> None:
        rows = [
            {
                "run_id": "run1", "collected_at": "2026-04-28 10:00:00", "source": "betano",
                "league": "Liga Test", "match_datetime": "2026-04-28 15:00", "home_team": "A", "away_team": "B",
                "match_name": "A - B", "market_raw": "Total de Gols Mais/Menos", "selection_raw": "Mais de 2.5",
                "odd": 2.0, "event_url": "http://example.com",
                "market_type": "total_goals", "market_scope": "full_time", "side": "over",
                "line": 2.5, "target_team_role": "geral", "target_team_name": "geral", "normalized_status": "ok",
            }
        ]
        diag = {
            "success": True,
            "raw_markets_seen": 5,
            "raw_selections_seen": 20,
            "supported_market_rows_seen": 10,
            "supported_market_rows_with_valid_odd": 5,
            "normalized_ok_rows": 5,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {"Total de Gols Mais/Menos": 1},
            "markets_seen_by_type_id": {13: 1},
            "failure_reason": None,
        }
        run_dir, exit_code = self._run_collector(
            mock_ligas=[{"nome": "Liga Test", "path": "/liga/test"}],
            mock_extract_side_effect=[(rows, diag)],
        )
        self.assertIsNone(exit_code)
        manifest_path = run_dir / "odds_collection_manifest.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertIn("run_id", m)
        self.assertIn("target_date", m)
        self.assertIn("totals", m)
        self.assertIn("leagues", m)
        self.assertIn("failure_reasons", m)
        self.assertIn("warnings", m)
        self.assertIn("Liga Test", m["leagues"])
        self.assertEqual(m["leagues"]["Liga Test"]["raw_selections_seen"], 20)
        self.assertEqual(m["fetch_method"], "event_api_odds_bt14")
        self.assertEqual(sorted(m["supported_market_type_ids"]), sorted(SUPPORTED_MARKET_TYPE_IDS.keys()))

    def test_semicolon_odds_snapshot_can_be_loaded_by_pipeline(self) -> None:
        rows = [
            {
                "run_id": "run1", "collected_at": "2026-04-28 10:00:00", "source": "betano",
                "league": "Liga Test", "match_datetime": "2026-04-28 15:00", "home_team": "A", "away_team": "B",
                "match_name": "A - B", "market_raw": "Total de Gols Mais/Menos", "selection_raw": "Mais de 2.5",
                "odd": 2.0, "event_url": "http://example.com",
                "market_type": "total_goals", "market_scope": "full_time", "side": "over",
                "line": 2.5, "target_team_role": "geral", "target_team_name": "geral", "normalized_status": "ok",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "odds_snapshot.csv"
            save_to_csv(rows, path)
            df = carregar_snapshot_odds(path)
            self.assertFalse(df.empty)
            self.assertIn("league", df.columns)
            self.assertIn("odd", df.columns)
            self.assertEqual(df.iloc[0]["odd"], 2.0)

    def test_no_final_rows_is_warning_not_failure(self) -> None:
        rows = []
        diag = {
            "success": True,
            "raw_markets_seen": 5,
            "raw_selections_seen": 20,
            "supported_market_rows_seen": 10,
            "supported_market_rows_with_valid_odd": 5,
            "normalized_ok_rows": 5,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {"Total de Gols Mais/Menos": 1},
            "markets_seen_by_type_id": {13: 1},
            "failure_reason": None,
        }
        run_dir, exit_code = self._run_collector(
            mock_ligas=[{"nome": "Liga Test", "path": "/liga/test"}],
            mock_extract_side_effect=[(rows, diag)],
        )
        self.assertIsNone(exit_code)
        manifest_path = run_dir / "odds_collection_manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual(m["status"], "completed")
        self.assertIn("no_final_rows_despite_supported_markets", m["warnings"])
        self.assertEqual(m["failure_reasons"], [])


class NormalizeByFamilyTest(unittest.TestCase):
    def test_typeid_13_total_goals_vs_typeid_189_asian_total(self) -> None:
        from vcbet.core.market_normalizer import normalize_market_entry

        # typeId=13 (Total de Gols Mais/Menos) -> total_goals
        r13 = normalize_market_entry(
            market_raw="Total de Gols Mais/Menos",
            selection_raw="Mais de 2.5",
            home_team="A",
            away_team="B",
            betano_market_type_id=13,
            betano_market_family="asian_total_or_total_ou",
        )
        self.assertEqual(r13["market_type"], "total_goals")
        self.assertEqual(r13["side"], "over")
        self.assertEqual(r13["line"], 2.5)

        # typeId=189 (Asiático Total de Gols) -> asian_total
        r189 = normalize_market_entry(
            market_raw="Asiático (Mais/Menos) Total de gols",
            selection_raw="Mais de 2.5",
            home_team="A",
            away_team="B",
            betano_market_type_id=189,
            betano_market_family="asian_total",
        )
        self.assertEqual(r189["market_type"], "asian_total")
        self.assertEqual(r189["side"], "over")
        self.assertEqual(r189["line"], 2.5)

    def test_typeid_84_home_team_total_vs_typeid_85_away_team_total(self) -> None:
        from vcbet.core.market_normalizer import normalize_market_entry

        # typeId=84 (Mandante Total) -> team_total home
        r84 = normalize_market_entry(
            market_raw="Time mandante Total de Gols Mais/Menos",
            selection_raw="Mais de 1.5",
            home_team="Flamengo",
            away_team="Palmeiras",
            betano_market_type_id=84,
            betano_market_family="home_team_total_ou",
        )
        self.assertEqual(r84["market_type"], "team_total")
        self.assertEqual(r84["side"], "over")
        self.assertEqual(r84["target_team_role"], "home")
        self.assertEqual(r84["target_team_name"], "Flamengo")

        # typeId=85 (Visitante Total) -> team_total away
        r85 = normalize_market_entry(
            market_raw="Time visitante Total de Gols Mais/Menos",
            selection_raw="Menos de 1.5",
            home_team="Flamengo",
            away_team="Palmeiras",
            betano_market_type_id=85,
            betano_market_family="away_team_total_ou",
        )
        self.assertEqual(r85["market_type"], "team_total")
        self.assertEqual(r85["side"], "under")
        self.assertEqual(r85["target_team_role"], "away")
        self.assertEqual(r85["target_team_name"], "Palmeiras")

    def test_family_btts_and_asian_handicap(self) -> None:
        from vcbet.core.market_normalizer import normalize_market_entry

        r15 = normalize_market_entry(
            market_raw="Ambas equipes Marcam",
            selection_raw="Sim",
            home_team="A",
            away_team="B",
            betano_market_type_id=15,
            betano_market_family="btts",
        )
        self.assertEqual(r15["market_type"], "btts")
        self.assertEqual(r15["side"], "yes")

        r185 = normalize_market_entry(
            market_raw="Handicap Asiático",
            selection_raw="A -1.5",
            home_team="A",
            away_team="B",
            betano_market_type_id=185,
            betano_market_family="asian_handicap",
        )
        self.assertEqual(r185["market_type"], "asian_handicap")
        self.assertEqual(r185["side"], "home")
        self.assertEqual(r185["line"], -1.5)

    def test_legacy_fallback_without_family(self) -> None:
        from vcbet.core.market_normalizer import normalize_market_entry

        r = normalize_market_entry(
            market_raw="Total de Gols Mais/Menos",
            selection_raw="Mais de 2.5",
            home_team="A",
            away_team="B",
        )
        self.assertEqual(r["market_type"], "total_goals")
        self.assertEqual(r["side"], "over")


if __name__ == "__main__":
    unittest.main()
