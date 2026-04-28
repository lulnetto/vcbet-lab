from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FOOTYSTATS_BASE_URL = "https://footystats.org"
DEFAULT_WARMUP_URL = "https://footystats.org/"

_BLOCK_PAGE_PATTERNS = [
    re.compile(r"403", re.IGNORECASE),
    re.compile(r"Forbidden", re.IGNORECASE),
    re.compile(r"Access denied", re.IGNORECASE),
    re.compile(r"Cloudflare", re.IGNORECASE),
    re.compile(r"Just a moment", re.IGNORECASE),
    re.compile(r"captcha", re.IGNORECASE),
]


def _is_blocked_page(html: str | None) -> bool:
    if not html:
        return True
    text = html[:8000]
    for pattern in _BLOCK_PAGE_PATTERNS:
        if pattern.search(text):
            return True
    return False


@dataclass
class FetchResult:
    ok: bool
    url: str
    status_code: int | None
    html: str | None
    method: str
    error: str | None = None


class FootyStatsBrowserFetcher:
    """Browser-based fetcher for FootyStats with warm-up and context reuse.

    Reuses one browser context for all fetches within a single run.
    Supports persistent profile directories for session reuse.
    """

    def __init__(
        self,
        *,
        warmup_url: str = DEFAULT_WARMUP_URL,
        headless: bool = True,
        timeout_ms: int = 30000,
        warmup_wait_ms: int = 2500,
        debug: bool = False,
        profile_dir: str | Path | None = None,
    ) -> None:
        self.warmup_url = warmup_url
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.warmup_wait_ms = warmup_wait_ms
        self.debug = debug
        self.profile_dir = Path(profile_dir) if profile_dir else None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "FootyStatsBrowserFetcher":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "footystats_browser_unavailable: Playwright não está instalado. "
                "Instale com `pip install playwright` e `playwright install chromium`."
            ) from exc

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        except Exception as exc:
            raise RuntimeError(
                "footystats_browser_unavailable: Chromium do Playwright não está disponível. "
                "Rode `playwright install chromium`."
            ) from exc

        context_kwargs: dict[str, Any] = {
            "locale": "en-US",
            "timezone_id": "Europe/London",
            "ignore_https_errors": True,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1920, "height": 1080},
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-GPC": "1",
            },
        }
        if self.profile_dir is not None:
            context_kwargs["storage_state"] = str(self.profile_dir) if self.profile_dir.exists() else None

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self.timeout_ms)
        self._page = self._context.new_page()

        print("[browser_warmup_started] FootyStats warm-up")
        self._page.goto(self.warmup_url, wait_until="domcontentloaded")
        try:
            self._page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 8000))
        except Exception:
            pass
        if self.warmup_wait_ms > 0:
            self._page.wait_for_timeout(self.warmup_wait_ms)
        print("[browser_warmup_success] FootyStats warm-up complete")
        if self.debug:
            print(f"[DEBUG] Browser warmup OK em: {self.warmup_url}")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for obj in (self._page, self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

    def fetch_html(self, url: str) -> FetchResult:
        if self._page is None:
            return FetchResult(
                ok=False,
                url=url,
                status_code=None,
                html=None,
                method="browser",
                error="Browser page not initialized",
            )

        print(f"[browser_fetch_started] {url}")
        try:
            response = self._page.goto(url, wait_until="domcontentloaded")
            status_code = response.status if response is not None else 200
            try:
                self._page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 10000))
            except Exception:
                pass
            html = self._page.content()

            if status_code >= 400:
                if status_code == 403:
                    print(f"[browser_fetch_forbidden] {url} status={status_code}")
                    return FetchResult(
                        ok=False,
                        url=url,
                        status_code=status_code,
                        html=html,
                        method="browser",
                        error="footystats_browser_forbidden_403",
                    )
                print(f"[browser_fetch_failed] {url} status={status_code}")
                return FetchResult(
                    ok=False,
                    url=url,
                    status_code=status_code,
                    html=html,
                    method="browser",
                    error=f"HTTP {status_code}",
                )

            if _is_blocked_page(html):
                print(f"[browser_fetch_blocked] {url} block_page_detected")
                return FetchResult(
                    ok=False,
                    url=url,
                    status_code=status_code,
                    html=html,
                    method="browser",
                    error="footystats_block_page_detected",
                )

            print(f"[browser_fetch_success] {url} status={status_code}")
            return FetchResult(
                ok=True,
                url=url,
                status_code=status_code,
                html=html,
                method="browser",
                error=None,
            )
        except Exception as exc:
            print(f"[browser_fetch_failed] {url} error={exc}")
            return FetchResult(
                ok=False,
                url=url,
                status_code=None,
                html=None,
                method="browser",
                error=str(exc),
            )

    def save_debug_artifact(self, url: str, debug_dir: Path, slug: str) -> dict[str, Path | None]:
        """Save HTML and optional screenshot for diagnostic purposes."""
        debug_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path | None] = {"html": None, "screenshot": None}

        if self._page is None:
            return paths

        html_path = debug_dir / f"footystats_{slug}_blocked.html"
        try:
            html = self._page.content()
            html_path.write_text(html, encoding="utf-8")
            paths["html"] = html_path
            print(f"[browser_debug_saved] HTML: {html_path}")
        except Exception as exc:
            print(f"[browser_debug_failed] HTML save error: {exc}")

        screenshot_path = debug_dir / f"footystats_{slug}_blocked.png"
        try:
            self._page.screenshot(path=str(screenshot_path), full_page=True)
            paths["screenshot"] = screenshot_path
            print(f"[browser_debug_saved] Screenshot: {screenshot_path}")
        except Exception as exc:
            print(f"[browser_debug_failed] Screenshot error: {exc}")

        return paths
