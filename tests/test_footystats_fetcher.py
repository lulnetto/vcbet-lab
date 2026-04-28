from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vcbet.collectors.footystats_fetcher import FetchResult, FootyStatsBrowserFetcher


class FootyStatsBrowserFetcherTest(unittest.TestCase):
    def _make_mocked_fetcher(self, html: str = "<html></html>", status: int = 200) -> FootyStatsBrowserFetcher:
        fetcher = FootyStatsBrowserFetcher()
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_response = MagicMock()

        mock_response.status = status
        mock_page.goto.return_value = mock_response
        mock_page.content.return_value = html
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_playwright.chromium.launch.return_value = mock_browser

        fetcher._playwright = mock_playwright
        fetcher._browser = mock_browser
        fetcher._context = mock_context
        fetcher._page = mock_page
        return fetcher

    def test_fetch_html_returns_ok_with_content(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html><body>test</body></html>")
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.html, "<html><body>test</body></html>")
        self.assertEqual(result.method, "browser")
        self.assertIsNone(result.error)

    def test_fetch_html_logs_success(self) -> None:
        fetcher = self._make_mocked_fetcher()
        with patch("builtins.print") as mock_print:
            fetcher.fetch_html("https://footystats.org/liga/xg")

        printed = [call.args[0] for call in mock_print.call_args_list if call.args]
        self.assertTrue(any("[browser_fetch_started]" in str(p) for p in printed))
        self.assertTrue(any("[browser_fetch_success]" in str(p) for p in printed))

    def test_fetch_html_403_returns_ok_false(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html>403 Forbidden</html>", status=403)
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.error, "footystats_browser_forbidden_403")
        self.assertIsNotNone(result.html)

    def test_fetch_html_403_logs_forbidden_not_success(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html>403 Forbidden</html>", status=403)
        with patch("builtins.print") as mock_print:
            fetcher.fetch_html("https://footystats.org/liga/xg")

        printed = [str(call.args[0]) for call in mock_print.call_args_list if call.args]
        self.assertTrue(any("[browser_fetch_forbidden]" in p for p in printed))
        self.assertFalse(any("[browser_fetch_success]" in p for p in printed))

    def test_fetch_html_500_returns_ok_false(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html>Internal Server Error</html>", status=500)
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 500)
        self.assertEqual(result.error, "HTTP 500")

    def test_fetch_html_detects_block_page_even_on_200(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html><body>Just a moment... Cloudflare</body></html>", status=200)
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.error, "footystats_block_page_detected")

    def test_fetch_html_detects_access_denied(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html><body>Access denied</body></html>", status=200)
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "footystats_block_page_detected")

    def test_enter_starts_browser_and_goes_to_warmup(self) -> None:
        mock_sync_playwright = MagicMock()
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_response = MagicMock()

        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_sync_playwright.start.return_value = mock_playwright

        with patch(
            "playwright.sync_api.sync_playwright",
            return_value=mock_sync_playwright,
        ):
            fetcher = FootyStatsBrowserFetcher()
            with patch("builtins.print"):
                fetcher.__enter__()

        mock_sync_playwright.start.assert_called_once()
        mock_playwright.chromium.launch.assert_called_once()
        mock_browser.new_context.assert_called_once()
        mock_context.new_page.assert_called_once()
        mock_page.goto.assert_called_once_with("https://footystats.org/", wait_until="domcontentloaded")

    def test_enter_uses_profile_dir_when_provided(self) -> None:
        mock_sync_playwright = MagicMock()
        mock_playwright = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_response = MagicMock()

        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_sync_playwright.start.return_value = mock_playwright

        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile"
            with patch(
                "playwright.sync_api.sync_playwright",
                return_value=mock_sync_playwright,
            ):
                fetcher = FootyStatsBrowserFetcher(profile_dir=profile)
                with patch("builtins.print"):
                    fetcher.__enter__()

        call_kwargs = mock_browser.new_context.call_args.kwargs
        self.assertEqual(call_kwargs.get("locale"), "en-US")
        self.assertEqual(call_kwargs.get("timezone_id"), "Europe/London")
        self.assertIn("viewport", call_kwargs)

    def test_enter_raises_when_playwright_missing(self) -> None:
        def _fake_import(name, *args, **kwargs):
            if name == "playwright.sync_api":
                raise ImportError("No module named 'playwright'")
            return __builtins__["__import__"](name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            fetcher = FootyStatsBrowserFetcher()
            with self.assertRaises(RuntimeError) as ctx:
                fetcher.__enter__()

        self.assertIn("footystats_browser_unavailable", str(ctx.exception))

    def test_enter_raises_when_chromium_missing(self) -> None:
        mock_sync_playwright = MagicMock()
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch.side_effect = Exception("Executable doesn't exist")
        mock_sync_playwright.start.return_value = mock_playwright

        with patch(
            "playwright.sync_api.sync_playwright",
            return_value=mock_sync_playwright,
        ):
            fetcher = FootyStatsBrowserFetcher()
            with self.assertRaises(RuntimeError) as ctx:
                fetcher.__enter__()

        self.assertIn("footystats_browser_unavailable", str(ctx.exception))

    def test_exit_closes_resources(self) -> None:
        fetcher = self._make_mocked_fetcher()
        fetcher.__exit__(None, None, None)

        fetcher._page.close.assert_called_once()
        fetcher._context.close.assert_called_once()
        fetcher._browser.close.assert_called_once()
        fetcher._playwright.stop.assert_called_once()

    def test_fetch_html_returns_error_when_page_not_initialized(self) -> None:
        fetcher = FootyStatsBrowserFetcher()
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertFalse(result.ok)
        self.assertIn("not initialized", result.error or "")

    def test_fetch_html_returns_error_on_exception(self) -> None:
        fetcher = self._make_mocked_fetcher()
        fetcher._page.goto.side_effect = Exception("Navigation timeout")
        result = fetcher.fetch_html("https://footystats.org/liga/xg")

        self.assertFalse(result.ok)
        self.assertIn("Navigation timeout", result.error or "")

    def test_save_debug_artifact_saves_html_and_screenshot(self) -> None:
        fetcher = self._make_mocked_fetcher(html="<html>blocked</html>")
        with tempfile.TemporaryDirectory() as tmp:
            debug_dir = Path(tmp)
            paths = fetcher.save_debug_artifact("https://footystats.org/liga/xg", debug_dir, "liga_teste")

            self.assertIsNotNone(paths.get("html"))
            self.assertTrue(paths["html"].exists())
            self.assertEqual(paths["html"].read_text(), "<html>blocked</html>")
        fetcher._page.screenshot.assert_called_once()

    def test_save_debug_artifact_returns_empty_when_page_none(self) -> None:
        fetcher = FootyStatsBrowserFetcher()
        with tempfile.TemporaryDirectory() as tmp:
            debug_dir = Path(tmp)
            paths = fetcher.save_debug_artifact("https://example.com", debug_dir, "slug")
        self.assertIsNone(paths["html"])
        self.assertIsNone(paths["screenshot"])


class FetchResultDataclassTest(unittest.TestCase):
    def test_fetch_result_fields(self) -> None:
        result = FetchResult(
            ok=True,
            url="https://example.com",
            status_code=200,
            html="<html></html>",
            method="browser",
            error=None,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.url, "https://example.com")
        self.assertEqual(result.status_code, 200)


if __name__ == "__main__":
    unittest.main()
