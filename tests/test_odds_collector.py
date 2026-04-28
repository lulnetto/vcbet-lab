from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vcbet.collectors.odds_collector import (
    BetanoExtractor,
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


class MockResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class BetanoExtractorFetchTest(unittest.TestCase):
    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_non_2xx_league_page_is_rejected_and_retried(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        # First two calls return 500, third returns 200 with valid state
        responses = [
            MockResponse(500, "error"),
            MockResponse(500, "error"),
            MockResponse(200, 'window["initial_state"]={"data":{"blocks":[]}};'),
        ]
        session.get.side_effect = responses
        # We test via get_match_urls_by_date
        urls, diag = extractor.get_match_urls_by_date("/liga/teste", "2026-04-28")
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual(urls, [])
        self.assertTrue(diag["success"])

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_event_page_without_initial_state_is_failure(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        session.get.return_value = MockResponse(200, '<html><body>no state</body></html>')
        rows, diag = extractor.extract_all_odds("/match/test", 1.66, "Liga", "run1")
        self.assertEqual(rows, [])
        self.assertFalse(diag["success"])
        self.assertIn("missing_initial_state", diag["failure_reason"])


class BetanoExtractorParsingTest(unittest.TestCase):
    def _build_event_html(self, markets: list) -> str:
        state = {
            "data": {
                "event": {
                    "id": "evt1",
                    "leagueId": "lig1",
                    "name": "Team A - Team B",
                    "startTime": 1714309200000,
                    "marketsCount": len(markets),
                    "markets": markets,
                }
            }
        }
        return 'window["initial_state"]=' + json.dumps(state) + ";"

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_market_selections_parses_hctg_btsc_mres(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        markets = [
            {
                "id": "m1",
                "name": "Total de Gols Mais/Menos",
                "type": "MRES",
                "typeId": 1,
                "selections": [
                    {"id": "s1", "name": "Mais de 2.5", "price": 2.0, "betRef": "b1"}
                ],
            },
            {
                "id": "m2",
                "name": "Ambas equipes Marcam",
                "type": "BTSC",
                "typeId": 2,
                "selections": [
                    {"id": "s2", "name": "Sim", "price": 1.8, "betRef": "b2"}
                ],
            },
            {
                "id": "m3",
                "name": "Handicap Asiático",
                "type": "HCTG",
                "typeId": 3,
                "selections": [
                    {"id": "s3", "name": "Team A -1.5", "price": 2.2, "betRef": "b3"}
                ],
            },
        ]
        session.get.return_value = MockResponse(200, self._build_event_html(markets))
        rows, diag = extractor.extract_all_odds("/match/test", 1.66, "Liga", "run1")
        self.assertTrue(diag["success"])
        types = {r["betano_market_type"] for r in rows}
        self.assertIn("MRES", types)
        self.assertIn("BTSC", types)
        self.assertIn("HCTG", types)
        self.assertGreaterEqual(len(rows), 3)

    @patch("vcbet.collectors.odds_collector.requests.Session")
    def test_tablelayout_selections_are_parsed(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        mock_session_cls.return_value = session
        extractor = BetanoExtractor()
        markets = [
            {
                "id": "m4",
                "name": "Total de Gols Mais/Menos",
                "type": "MRES",
                "typeId": 1,
                "tableLayout": {
                    "rows": [
                        {
                            "name": "Row1",
                            "groupSelections": [
                                {
                                    "name": "Group1",
                                    "selections": [
                                        {"id": "s4", "name": "Menos de 2.5", "price": 1.9, "betRef": "b4"}
                                    ],
                                }
                            ],
                        }
                    ]
                },
            }
        ]
        session.get.return_value = MockResponse(200, self._build_event_html(markets))
        rows, diag = extractor.extract_all_odds("/match/test", 1.66, "Liga", "run1")
        self.assertTrue(diag["success"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["betano_table_row_name"], "Row1")
        self.assertEqual(rows[0]["betano_group_name"], "Group1")
        self.assertEqual(rows[0]["betano_selection_id"], "s4")


class CollectorMainBlockTest(unittest.TestCase):
    def _run_collector(self, mock_ligas: list, mock_extract_side_effect: list, min_odd: float = 1.66, extra_args: list | None = None):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_id = "test_run_001"
            args = [
                "odds_collector.py",
                "--run-id", run_id,
                "--d", "2026-04-28",
                "--output-dir", tmpdir,
            ] + (extra_args or [])
            with patch.object(sys, "argv", args):
                with patch("vcbet.collectors.odds_collector.carregar_ligas_betano", return_value=mock_ligas):
                    with patch("vcbet.collectors.odds_collector.requests.Session") as mock_session_cls:
                        session = MagicMock()
                        mock_session_cls.return_value = session
                        # get_match_urls_by_date will use _fetch, which calls session.get
                        # We can patch BetanoExtractor.get_match_urls_by_date directly to avoid full HTML mocking
                        with patch.object(BetanoExtractor, "get_match_urls_by_date", return_value=(["/match/1"], {"success": True, "events_found": 1})):
                            with patch.object(BetanoExtractor, "extract_all_odds", side_effect=mock_extract_side_effect):
                                # Need to import and run main block
                                import importlib
                                import vcbet.collectors.odds_collector as oc
                                importlib.reload(oc)
                                try:
                                    oc.main()  # wait, there is no main() function, it's under if __name__ == "__main__"
                                except SystemExit as exc:
                                    return Path(tmpdir) / "2026-04-28" / run_id, exc.code
            # If no SystemExit, return run_dir and None
            return Path(tmpdir) / "2026-04-28" / run_id, None

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
        # One event, failure -> event_failure_rate = 1.0 > 0.25
        diag = {
            "success": False,
            "raw_markets_seen": 0,
            "raw_selections_seen": 0,
            "supported_market_rows_before_min_odd": 0,
            "rows_after_min_odd_filter": 0,
            "normalized_ok_rows": 0,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {},
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
            "supported_market_rows_before_min_odd": 10,
            "rows_after_min_odd_filter": 5,
            "normalized_ok_rows": 5,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {"Total de Gols Mais/Menos": 1},
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
            "supported_market_rows_before_min_odd": 10,
            "rows_after_min_odd_filter": 5,
            "normalized_ok_rows": 5,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {"Total de Gols Mais/Menos": 1},
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

    def test_min_odd_filtered_rows_is_warning_not_failure(self) -> None:
        # simulate rows below min_odd: supported rows exist but none pass min_odd
        rows = []
        diag = {
            "success": True,
            "raw_markets_seen": 5,
            "raw_selections_seen": 20,
            "supported_market_rows_before_min_odd": 10,
            "rows_after_min_odd_filter": 0,
            "normalized_ok_rows": 5,
            "normalized_non_ok_rows": 0,
            "markets_seen_by_name": {"Total de Gols Mais/Menos": 1},
            "failure_reason": None,
        }
        run_dir, exit_code = self._run_collector(
            mock_ligas=[{"nome": "Liga Test", "path": "/liga/test"}],
            mock_extract_side_effect=[(rows, diag)],
        )
        # health_ok should be True because raw data is healthy; only warning about min_odd
        self.assertIsNone(exit_code)
        manifest_path = run_dir / "odds_collection_manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual(m["status"], "completed")
        self.assertIn("min_odd_filtered_all_supported_rows", m["warnings"])
        self.assertEqual(m["failure_reasons"], [])


if __name__ == "__main__":
    unittest.main()
