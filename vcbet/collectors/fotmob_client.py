from __future__ import annotations

from dataclasses import dataclass

import requests


FOTMOB_BASE_URL = "https://www.fotmob.com"
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass
class FotMobFetchResult:
    ok: bool
    url: str
    status_code: int | None
    json_data: dict | None
    method: str
    error: str | None = None


class FotMobClient:
    """HTTP client for FotMob league data API."""

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.fotmob.com/",
            }
        )

    def warmup(self) -> FotMobFetchResult:
        url = f"{FOTMOB_BASE_URL}/"
        try:
            response = self._session.get(url, timeout=self.timeout_seconds)
            if response.status_code >= 400:
                return FotMobFetchResult(
                    ok=False,
                    url=url,
                    status_code=response.status_code,
                    json_data=None,
                    method="requests",
                    error=f"warmup HTTP {response.status_code}",
                )
            return FotMobFetchResult(
                ok=True,
                url=url,
                status_code=response.status_code,
                json_data=None,
                method="requests",
                error=None,
            )
        except Exception as exc:
            return FotMobFetchResult(
                ok=False,
                url=url,
                status_code=None,
                json_data=None,
                method="requests",
                error=str(exc),
            )

    def fetch_league_data(self, league_id: int, ccode3: str) -> FotMobFetchResult:
        url = f"{FOTMOB_BASE_URL}/api/data/leagues"
        params = {"id": str(league_id), "ccode3": ccode3}
        try:
            response = self._session.get(url, params=params, timeout=self.timeout_seconds)
            if response.status_code >= 400:
                return FotMobFetchResult(
                    ok=False,
                    url=response.url,
                    status_code=response.status_code,
                    json_data=None,
                    method="requests",
                    error=f"HTTP {response.status_code}",
                )
            try:
                data = response.json()
            except Exception as exc:
                return FotMobFetchResult(
                    ok=False,
                    url=response.url,
                    status_code=response.status_code,
                    json_data=None,
                    method="requests",
                    error=f"JSON decode failed: {exc}",
                )
            return FotMobFetchResult(
                ok=True,
                url=response.url,
                status_code=response.status_code,
                json_data=data,
                method="requests",
                error=None,
            )
        except Exception as exc:
            return FotMobFetchResult(
                ok=False,
                url=url,
                status_code=None,
                json_data=None,
                method="requests",
                error=str(exc),
            )
