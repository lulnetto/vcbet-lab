#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


def extract_initial_state(text: str) -> dict:
    marker = 'window["initial_state"]='
    marker_idx = text.find(marker)
    if marker_idx < 0:
        raise RuntimeError("initial_state not found")

    json_start = text.find("{", marker_idx + len(marker))
    if json_start < 0:
        raise RuntimeError("initial_state JSON start not found")

    depth = 0
    in_string = False
    escape = False

    for idx in range(json_start, len(text)):
        ch = text[idx]

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
                raw = text[json_start:idx + 1]
                return json.loads(html.unescape(raw))

    raise RuntimeError("initial_state JSON end not found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True)
    parser.add_argument("--out-txt", required=True)
    parser.add_argument("--out-csv", required=True)
    args = parser.parse_args()

    html_path = Path(args.html)
    out_txt = Path(args.out_txt)
    out_csv = Path(args.out_csv)

    text = html_path.read_text(encoding="utf-8", errors="replace")
    data = extract_initial_state(text)

    event = data["data"]["event"]
    participants = event.get("participants", [])
    home = participants[0].get("name", "") if len(participants) > 0 else ""
    away = participants[1].get("name", "") if len(participants) > 1 else ""

    rows = []

    def add_selection(market: dict, selection: dict, extra: dict | None = None) -> None:
        price = selection.get("price")
        if price in (None, "", 0):
            return

        row = {
            "event_id": event.get("id"),
            "league_id": event.get("leagueId"),
            "league": event.get("leagueName") or event.get("leagueDescription"),
            "home": home,
            "away": away,
            "start_time": event.get("startTime"),
            "event_url": event.get("url"),
            "total_markets_available": event.get("totalMarketsAvailable"),
            "market_id": market.get("id"),
            "market_name": market.get("name"),
            "market_type": market.get("type"),
            "market_type_id": market.get("typeId"),
            "market_handicap": market.get("handicap"),
            "selection_id": selection.get("id"),
            "selection_name": selection.get("name"),
            "selection_full_name": selection.get("fullName") or selection.get("shortName") or selection.get("name"),
            "selection_price": price,
            "selection_handicap": selection.get("handicap"),
            "bet_ref": selection.get("betRef"),
            "source_shape": "market.selections",
        }
        if extra:
            row.update(extra)
        rows.append(row)

    for market in event.get("markets", []) or []:
        for sel in market.get("selections", []) or []:
            add_selection(market, sel)

        table = market.get("tableLayout") or {}
        for tr in table.get("rows", []) or []:
            for gs in tr.get("groupSelections", []) or []:
                for sel in gs.get("selections", []) or []:
                    add_selection(
                        market,
                        sel,
                        {
                            "source_shape": "tableLayout.rows.groupSelections",
                            "table_title": table.get("title"),
                            "table_row_id": tr.get("rowId"),
                            "table_row_title": tr.get("title"),
                            "table_group_id": tr.get("groupId"),
                            "group_line": gs.get("line"),
                            "group_handicap": gs.get("handicap"),
                        },
                    )

    fieldnames = sorted({key for row in rows for key in row})
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    by_type = {}
    for row in rows:
        key = (row.get("market_type"), row.get("market_name"))
        by_type[key] = by_type.get(key, 0) + 1

    with out_txt.open("w", encoding="utf-8") as f:
        f.write(f"HTML={html_path}\n")
        f.write(f"CSV={out_csv}\n")
        f.write(f"event_id={event.get('id')}\n")
        f.write(f"event_name={event.get('name') or event.get('shortName')}\n")
        f.write(f"league={event.get('leagueName')}\n")
        f.write(f"home={home}\n")
        f.write(f"away={away}\n")
        f.write(f"totalMarketsAvailable={event.get('totalMarketsAvailable')}\n")
        f.write(f"markets_count={len(event.get('markets', []) or [])}\n")
        f.write(f"rows={len(rows)}\n\n")

        f.write("=== ROWS BY MARKET TYPE ===\n")
        for (market_type, name), count in sorted(by_type.items(), key=lambda item: (-item[1], str(item[0]))):
            f.write(f"{count} | {market_type} | {name}\n")

        f.write("\n=== SAMPLE ROWS ===\n")
        for row in rows[:80]:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

        f.write("\n=== DONE ===\n")

    print(out_txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
