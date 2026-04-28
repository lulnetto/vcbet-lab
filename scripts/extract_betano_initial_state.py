#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import requests


def extract_initial_state(page_html: str) -> dict:
    marker = 'window["initial_state"]='
    marker_idx = page_html.find(marker)

    if marker_idx < 0:
        raise RuntimeError("initial_state não encontrado")

    json_start = page_html.find("{", marker_idx + len(marker))
    if json_start < 0:
        raise RuntimeError("início do JSON não encontrado")

    depth = 0
    in_string = False
    escape = False

    for idx in range(json_start, len(page_html)):
        ch = page_html[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw_json = page_html[json_start:idx + 1]
                return json.loads(html.unescape(raw_json))

    raise RuntimeError("fim do JSON não encontrado")


def fetch_html(url: str) -> str:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.betano.bet.br/",
    })

    session.get("https://www.betano.bet.br/", timeout=30)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", default="initial_state.json")
    args = parser.parse_args()

    page_html = fetch_html(args.url)
    data = extract_initial_state(page_html)

    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    event = data.get("data", {}).get("event", {})
    print("saved:", out)
    print("event_id:", event.get("id"))
    print("event_name:", event.get("name") or event.get("shortName"))
    print("league:", event.get("leagueName"))
    print("markets:", len(event.get("markets", []) or []))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
