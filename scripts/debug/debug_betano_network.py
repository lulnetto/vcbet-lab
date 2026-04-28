#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_PATTERNS = [
    "odds",
    "market",
    "markets",
    "event",
    "events",
    "fixture",
    "fixtures",
    "coupon",
    "prematch",
    "sportsbook",
    "betting",
    "betano",
    "api",
]


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def safe_name(url: str, suffix: str = ".txt") -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", url[:90]).strip("_")
    return f"{cleaned}_{digest}{suffix}"


def should_capture(
    url: str,
    resource_type: str | None,
    content_type: str | None,
    patterns: list[str],
    all_traffic: bool,
) -> bool:
    if all_traffic:
        return True

    haystack = f"{url} {resource_type or ''} {content_type or ''}".lower()
    if resource_type in {"xhr", "fetch"}:
        return True

    return any(p.lower() in haystack for p in patterns)


def write_jsonl(handle, payload: dict) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    handle.flush()


def build_target_url(args: argparse.Namespace) -> str:
    if args.url:
        return args.url

    if args.betano_path:
        return urljoin(args.base_url.rstrip("/") + "/", args.betano_path.lstrip("/"))

    raise SystemExit("Informe --url ou --betano-path.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Debug de network/XHR/fetch da Betano com Playwright. Não coleta odds, só registra tráfego."
    )

    parser.add_argument("--url", help="URL completa da página da Betano.")
    parser.add_argument("--betano-path", help="Path vindo do ligas.json, ex: /sport/futebol/inglaterra/championship/2/")
    parser.add_argument("--base-url", default="https://www.betano.bet.br", help="Base URL usada com --betano-path.")

    parser.add_argument("--output-dir", default="data/debug/betano_network")
    parser.add_argument("--run-id", default=None)

    parser.add_argument("--headed", action="store_true", help="Abre navegador visível. Em WSL pode exigir WSLg/Xvfb.")
    parser.add_argument("--profile-dir", default=None, help="Diretório de perfil persistente do browser.")
    parser.add_argument("--duration", type=int, default=45, help="Segundos para manter a página aberta capturando tráfego.")
    parser.add_argument("--post-load-wait", type=int, default=5, help="Segundos extras depois do carregamento inicial.")

    parser.add_argument("--scroll-steps", type=int, default=6, help="Quantidade de scrolls automáticos.")
    parser.add_argument("--scroll-px", type=int, default=1200, help="Pixels por scroll.")
    parser.add_argument("--no-scroll", action="store_true")

    parser.add_argument("--save-body", action="store_true", help="Salva preview de respostas JSON/texto suspeitas.")
    parser.add_argument("--body-limit", type=int, default=50000, help="Limite de chars por body salvo.")
    parser.add_argument("--all-traffic", action="store_true", help="Registra todo tráfego, não só suspeitos.")
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Padrão extra para filtrar URLs. Pode repetir. Ex: --pattern coupon --pattern markets",
    )

    args = parser.parse_args()

    target_url = build_target_url(args)
    run_id = args.run_id or f"betano_network_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    out_dir = Path(args.output_dir) / run_id
    bodies_dir = out_dir / "bodies"
    out_dir.mkdir(parents=True, exist_ok=True)
    bodies_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / "network_log.jsonl"
    suspects_path = out_dir / "suspect_endpoints.txt"
    html_path = out_dir / "page_final.html"
    screenshot_path = out_dir / "page_final.png"

    patterns = DEFAULT_PATTERNS + args.pattern
    seen_urls: dict[str, dict] = {}

    print(f"[debug] target_url: {target_url}")
    print(f"[debug] output_dir: {out_dir}")
    print(f"[debug] headed: {args.headed}")
    print(f"[debug] profile_dir: {args.profile_dir or '-'}")
    print("[debug] capturando network...")

    with log_path.open("w", encoding="utf-8") as log:
        with sync_playwright() as pw:
            browser = None
            context = None

            context_kwargs = {
                "locale": "pt-BR",
                "timezone_id": "America/Sao_Paulo",
                "viewport": {"width": 1440, "height": 1000},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "extra_http_headers": {
                    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            }

            if args.profile_dir:
                Path(args.profile_dir).mkdir(parents=True, exist_ok=True)
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=args.profile_dir,
                    headless=not args.headed,
                    **context_kwargs,
                )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = pw.chromium.launch(headless=not args.headed)
                context = browser.new_context(**context_kwargs)
                page = context.new_page()

            def on_request(request):
                try:
                    payload = {
                        "ts": now_iso(),
                        "type": "request",
                        "method": request.method,
                        "resource_type": request.resource_type,
                        "url": request.url,
                    }

                    if should_capture(request.url, request.resource_type, None, patterns, args.all_traffic):
                        write_jsonl(log, payload)
                except Exception as exc:
                    print(f"[warn] request callback failed: {exc}", file=sys.stderr)

            def on_response(response):
                try:
                    req = response.request
                    content_type = response.headers.get("content-type", "")
                    capture = should_capture(response.url, req.resource_type, content_type, patterns, args.all_traffic)

                    if not capture:
                        return

                    payload = {
                        "ts": now_iso(),
                        "type": "response",
                        "status": response.status,
                        "method": req.method,
                        "resource_type": req.resource_type,
                        "content_type": content_type,
                        "url": response.url,
                    }

                    body_file = None
                    if args.save_body and (
                        "json" in content_type.lower()
                        or "text" in content_type.lower()
                        or req.resource_type in {"xhr", "fetch"}
                    ):
                        try:
                            text = response.text()
                            if text:
                                body_file = bodies_dir / safe_name(response.url, ".txt")
                                body_file.write_text(text[: args.body_limit], encoding="utf-8", errors="replace")
                                payload["body_file"] = str(body_file)
                                payload["body_preview"] = text[:500]
                        except Exception as exc:
                            payload["body_error"] = str(exc)

                    write_jsonl(log, payload)

                    existing = seen_urls.get(response.url)
                    if not existing or response.status != existing.get("status"):
                        seen_urls[response.url] = {
                            "status": response.status,
                            "method": req.method,
                            "resource_type": req.resource_type,
                            "content_type": content_type,
                            "body_file": str(body_file) if body_file else None,
                        }

                    print(f"[{response.status}] {req.resource_type:>8} {response.url}")

                except Exception as exc:
                    print(f"[warn] response callback failed: {exc}", file=sys.stderr)

            page.on("request", on_request)
            page.on("response", on_response)

            try:
                print("[debug] warm-up Betano base...")
                try:
                    page.goto(args.base_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                except PlaywrightTimeoutError:
                    print("[warn] warm-up timeout; seguindo para target mesmo assim.")

                print("[debug] abrindo target...")
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(args.post_load_wait * 1000)

                if not args.no_scroll:
                    print("[debug] scroll automático...")
                    for i in range(args.scroll_steps):
                        page.mouse.wheel(0, args.scroll_px)
                        page.wait_for_timeout(1200)

                if args.headed:
                    print(f"[debug] navegador ficará aberto por {args.duration}s. Interaja manualmente se quiser.")
                else:
                    print(f"[debug] aguardando {args.duration}s em headless.")

                page.wait_for_timeout(args.duration * 1000)

                try:
                    html_path.write_text(page.content(), encoding="utf-8", errors="replace")
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"[debug] HTML final: {html_path}")
                    print(f"[debug] Screenshot final: {screenshot_path}")
                except Exception as exc:
                    print(f"[warn] falha salvando HTML/screenshot final: {exc}", file=sys.stderr)

            finally:
                with suspects_path.open("w", encoding="utf-8") as f:
                    for url, meta in sorted(seen_urls.items(), key=lambda kv: kv[0]):
                        f.write(
                            f"{meta.get('status')} | {meta.get('resource_type')} | "
                            f"{meta.get('content_type')} | {url}"
                        )
                        if meta.get("body_file"):
                            f.write(f" | body={meta['body_file']}")
                        f.write("\n")

                print(f"[debug] network log: {log_path}")
                print(f"[debug] suspect endpoints: {suspects_path}")
                print(f"[debug] endpoints únicos suspeitos: {len(seen_urls)}")

                context.close()
                if browser:
                    browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
