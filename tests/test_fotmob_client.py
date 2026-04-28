from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from vcbet.collectors.fotmob_client import FotMobClient, FotMobFetchResult


class FotMobClientTest(unittest.TestCase):
    def test_warmup_calls_fotmob_homepage(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, text="<html></html>")
            result = client.warmup()

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.url, "https://www.fotmob.com/")
        self.assertEqual(result.method, "requests")
        mock_get.assert_called_once_with("https://www.fotmob.com/", timeout=30)

    def test_warmup_non_2xx_returns_ok_false(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=403, text="Forbidden")
            result = client.warmup()

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertIn("403", result.error or "")

    def test_warmup_network_error_returns_ok_false(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_get.side_effect = Exception("Connection timeout")
            result = client.warmup()

        self.assertFalse(result.ok)
        self.assertIn("Connection timeout", result.error or "")

    def test_fetch_league_data_calls_correct_endpoint(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                url="https://www.fotmob.com/api/data/leagues?id=268&ccode3=BRA",
                json=lambda: {"details": {"name": "Brasileirão"}},
            )
            result = client.fetch_league_data(268, "BRA")

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json_data, {"details": {"name": "Brasileirão"}})
        mock_get.assert_called_once_with(
            "https://www.fotmob.com/api/data/leagues",
            params={"id": "268", "ccode3": "BRA"},
            timeout=30,
        )

    def test_fetch_league_data_non_2xx_returns_ok_false(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=500, text="Internal Server Error")
            result = client.fetch_league_data(268, "BRA")

        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 500)
        self.assertIn("500", result.error or "")

    def test_fetch_league_data_invalid_json_returns_ok_false(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_response = MagicMock(status_code=200)
            mock_response.json.side_effect = ValueError("No JSON")
            mock_get.return_value = mock_response
            result = client.fetch_league_data(268, "BRA")

        self.assertFalse(result.ok)
        self.assertIn("JSON decode failed", result.error or "")

    def test_fetch_league_data_network_error_returns_ok_false(self) -> None:
        client = FotMobClient()
        with patch.object(client._session, "get") as mock_get:
            mock_get.side_effect = Exception("DNS failure")
            result = client.fetch_league_data(268, "BRA")

        self.assertFalse(result.ok)
        self.assertIn("DNS failure", result.error or "")


class FotMobFetchResultDataclassTest(unittest.TestCase):
    def test_fields(self) -> None:
        result = FotMobFetchResult(
            ok=True,
            url="https://example.com",
            status_code=200,
            json_data={"a": 1},
            method="requests",
            error=None,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.url, "https://example.com")
        self.assertEqual(result.json_data, {"a": 1})


if __name__ == "__main__":
    unittest.main()
