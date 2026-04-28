from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from vcbet.collectors.footystats_xg_collector import (
    construir_banco_dados,
    extrair_dados_completos,
    _fetch_html,
    _slugify_league,
)


SAMPLE_HTML = """
<html>
<body>
<table class="full-league-table">
  <thead>
    <tr><th>Team</th><th>xG</th><th>xGA</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="team"><a href="/team/1">Team A</a></td>
      <td>1,50</td>
      <td>1,20</td>
    </tr>
    <tr>
      <td class="team"><a href="/team/2">Team B</a></td>
      <td>1,80</td>
      <td>1,40</td>
    </tr>
  </tbody>
</table>
<h3>xG Home</h3>
<ul class="ui-list">
  <li class="list-row">
    <div class="main"><a href="#">Team A</a></div>
    <div class="small-bubble">1.60</div>
  </li>
  <li class="list-row">
    <div class="main"><a href="#">Team B</a></div>
    <div class="small-bubble">1.90</div>
  </li>
</ul>
<h3>xG Away</h3>
<ul class="ui-list">
  <li class="list-row">
    <div class="main"><a href="#">Team A</a></div>
    <div class="small-bubble">1.40</div>
  </li>
  <li class="list-row">
    <div class="main"><a href="#">Team B</a></div>
    <div class="small-bubble">1.70</div>
  </li>
</ul>
<h3>xGA Home</h3>
<ul class="ui-list">
  <li class="list-row">
    <div class="main"><a href="#">Team A</a></div>
    <div class="small-bubble">1.10</div>
  </li>
  <li class="list-row">
    <div class="main"><a href="#">Team B</a></div>
    <div class="small-bubble">1.30</div>
  </li>
</ul>
<h3>xGA Away</h3>
<ul class="ui-list">
  <li class="list-row">
    <div class="main"><a href="#">Team A</a></div>
    <div class="small-bubble">1.30</div>
  </li>
  <li class="list-row">
    <div class="main"><a href="#">Team B</a></div>
    <div class="small-bubble">1.50</div>
  </li>
</ul>
</body>
</html>
"""


class FootyStatsXGParsingTest(unittest.TestCase):
    def test_extrair_dados_completos_parses_sample_html(self) -> None:
        df = extrair_dados_completos(SAMPLE_HTML)

        self.assertEqual(len(df), 2)
        self.assertIn("team_name", df.columns)
        self.assertIn("xg", df.columns)
        self.assertIn("xga", df.columns)
        self.assertIn("xg_home", df.columns)
        self.assertIn("xg_away", df.columns)
        self.assertIn("xga_home", df.columns)
        self.assertIn("xga_away", df.columns)

        row_a = df[df["team_name"] == "Team A"].iloc[0]
        self.assertAlmostEqual(row_a["xg"], 1.50)
        self.assertAlmostEqual(row_a["xga"], 1.20)
        self.assertAlmostEqual(row_a["xg_home"], 1.60)
        self.assertAlmostEqual(row_a["xg_away"], 1.40)
        self.assertAlmostEqual(row_a["xga_home"], 1.10)
        self.assertAlmostEqual(row_a["xga_away"], 1.30)

    def test_extrair_dados_completos_raises_on_missing_table(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extrair_dados_completos("<html></html>")
        self.assertIn("full-league-table", str(ctx.exception))


class FootyStatsXGBrowserModeTest(unittest.TestCase):
    def test_default_fetch_mode_is_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_browser_test"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=True, html=SAMPLE_HTML, status_code=200
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ) as mock_cls:
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                    )

            mock_cls.assert_called_once_with(debug=False, headless=True, profile_dir=None)
            mock_fetcher.__enter__.assert_called_once()
            mock_fetcher.__exit__.assert_called_once()
            mock_fetcher.fetch_html.assert_called_once_with("https://footystats.org/liga-teste/xg")

    def test_browser_fetch_failure_produces_no_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_browser_fail"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=False, html=None, status_code=None, error="Navigation timeout"
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())

    def test_all_fetches_forbidden_produces_no_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_all_403"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=False, html="<html>403 Forbidden</html>", status_code=403, error="footystats_browser_forbidden_403"
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {
                        "Liga A": "https://footystats.org/liga-a",
                        "Liga B": "https://footystats.org/liga-b",
                    }
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())
            # save_debug_artifact should be called for each failed league
            self.assertEqual(mock_fetcher.save_debug_artifact.call_count, 2)
            call_kwargs = mock_fetcher.save_debug_artifact.call_args.kwargs
            self.assertIn("slug", call_kwargs)
            self.assertIn("debug_dir", call_kwargs)

    def test_browser_mode_fails_explicitly_when_playwright_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_no_pw"
            target_date = "2026-04-24"

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                side_effect=RuntimeError("footystats_browser_unavailable"),
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    with self.assertRaises(RuntimeError) as ctx:
                        construir_banco_dados(
                            run_id=run_id,
                            target_date=target_date,
                            output_dir=output_dir,
                            ligas_alvo=None,
                            modo_debug=False,
                            fetch_mode="browser",
                        )

            self.assertIn("footystats_browser_unavailable", str(ctx.exception))
            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertFalse(snapshot_path.exists())

    def test_snapshot_keeps_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_cols"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=True, html=SAMPLE_HTML, status_code=200
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            self.assertTrue(snapshot_path.exists())
            df = pd.read_csv(snapshot_path, sep=";")
            required = {"run_id", "collected_at", "source", "league", "team_name", "xg", "xga", "xg_home", "xg_away", "xga_home", "xga_away"}
            self.assertTrue(required.issubset(set(df.columns)))

    def test_fetch_method_browser_attached_to_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_method"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=True, html=SAMPLE_HTML, status_code=200
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                    )

            snapshot_path = Path(output_dir) / target_date / run_id / "xg_snapshot.csv"
            df = pd.read_csv(snapshot_path, sep=";")
            self.assertTrue((df["fetch_method"] == "browser").all())

    def test_headed_flag_passed_to_fetcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_headed"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=True, html=SAMPLE_HTML, status_code=200
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ) as mock_cls:
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                        browser_headed=True,
                    )

            mock_cls.assert_called_once_with(debug=False, headless=False, profile_dir=None)

    def test_profile_dir_passed_to_fetcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            profile_dir = str(Path(tmp) / "browser_profile")
            run_id = "run_profile"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=True, html=SAMPLE_HTML, status_code=200
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ) as mock_cls:
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    construir_banco_dados(
                        run_id=run_id,
                        target_date=target_date,
                        output_dir=output_dir,
                        ligas_alvo=None,
                        modo_debug=False,
                        fetch_mode="browser",
                        browser_profile_dir=profile_dir,
                    )

            mock_cls.assert_called_once_with(debug=False, headless=True, profile_dir=profile_dir)

    def test_collector_skips_parser_when_fetch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_skip_parser"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=False, html=None, status_code=403, error="footystats_browser_forbidden_403"
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    with patch("vcbet.collectors.footystats_xg_collector.extrair_dados_completos") as mock_parser:
                        construir_banco_dados(
                            run_id=run_id,
                            target_date=target_date,
                            output_dir=output_dir,
                            ligas_alvo=None,
                            modo_debug=False,
                            fetch_mode="browser",
                        )
                        mock_parser.assert_not_called()


class FootyStatsXGFetchModeTest(unittest.TestCase):
    def test_requests_mode_uses_requests(self) -> None:
        with patch("vcbet.collectors.footystats_xg_collector._fetch_html_requests") as mock_requests:
            mock_requests.return_value = SAMPLE_HTML
            html = _fetch_html("https://example.com", fetch_mode="requests")
            mock_requests.assert_called_once()
            self.assertEqual(html, SAMPLE_HTML)

    def test_browser_first_falls_back_to_requests(self) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_html.return_value = MagicMock(
            ok=False, html=None, error="timeout"
        )

        with patch("vcbet.collectors.footystats_xg_collector._fetch_html_requests") as mock_requests:
            mock_requests.return_value = SAMPLE_HTML
            html = _fetch_html("https://example.com", fetch_mode="browser_first", fetcher=mock_fetcher)
            mock_fetcher.fetch_html.assert_called_once()
            mock_requests.assert_called_once()
            self.assertEqual(html, SAMPLE_HTML)

    def test_browser_only_requires_fetcher(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            _fetch_html("https://example.com", fetch_mode="browser")
        self.assertIn("footystats_browser_unavailable", str(ctx.exception))

    def test_unknown_fetch_mode_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _fetch_html("https://example.com", fetch_mode="unknown")
        self.assertIn("desconhecido", str(ctx.exception))


class FootyStatsXGDefaultPathTest(unittest.TestCase):
    def test_default_path_does_not_call_requests(self) -> None:
        """Default fetch_mode='browser' should not touch requests."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = tmp
            run_id = "run_default"
            target_date = "2026-04-24"

            mock_fetcher = MagicMock()
            mock_fetcher.fetch_html.return_value = MagicMock(
                ok=True, html=SAMPLE_HTML, status_code=200
            )

            with patch(
                "vcbet.collectors.footystats_xg_collector.FootyStatsBrowserFetcher",
                return_value=mock_fetcher,
            ):
                with patch("vcbet.collectors.footystats_xg_collector.carregar_ligas_footystats") as mock_ligas:
                    mock_ligas.return_value = {"Liga Teste": "https://footystats.org/liga-teste"}
                    with patch("vcbet.collectors.footystats_xg_collector._fetch_html_requests") as mock_requests:
                        construir_banco_dados(
                            run_id=run_id,
                            target_date=target_date,
                            output_dir=output_dir,
                            ligas_alvo=None,
                            modo_debug=False,
                        )
                        mock_requests.assert_not_called()


class FootyStatsSlugifyTest(unittest.TestCase):
    def test_slugify_replaces_special_chars(self) -> None:
        self.assertEqual(_slugify_league("Premier League"), "premier_league")
        self.assertEqual(_slugify_league("UEFA Champions League"), "uefa_champions_league")
        self.assertEqual(_slugify_league("Liga!!!"), "liga")


if __name__ == "__main__":
    unittest.main()
