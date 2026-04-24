#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_rows(path: Path) -> tuple[list[dict[str, str]], str, list[str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    rows = [{str(k): "" if v is None else str(v) for k, v in row.items() if k is not None} for row in reader]
    return rows, delimiter, list(reader.fieldnames or [])


def write_rows(path: Path, rows: list[dict[str, str]], delimiter: str, fieldnames: list[str]) -> None:
    if not rows:
        if path.exists():
            path.unlink()
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aprova aliases pendentes e atualiza alias_times.json")
    parser.add_argument("--pending-file", required=True)
    parser.add_argument("--alias-file", default="alias_times.json")
    parser.add_argument("--include-blocked", action="store_true")
    args = parser.parse_args()

    pending_file = Path(args.pending_file)
    alias_file = Path(args.alias_file)

    rows, delimiter, fieldnames = read_rows(pending_file)
    if not rows:
        print("Nenhuma linha no pending file.")
        if pending_file.exists():
            pending_file.unlink()
        return 0

    alias_map = {}
    if alias_file.exists():
        alias_map = json.loads(alias_file.read_text(encoding="utf-8"))

    remaining = []
    saved = 0
    for row in rows:
        status = str(row.get("match_status", "")).strip()
        visible = status == "pending_review" or (args.include_blocked and status == "blocked")
        if visible:
          source = str(row.get("source_name", "")).strip()
          target = str(row.get("suggestion", "")).strip()
          if source and target:
              alias_map[source] = target
              saved += 1
          continue
        remaining.append(row)

    alias_file.write_text(json.dumps(alias_map, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_rows(pending_file, remaining, delimiter, fieldnames)

    if not remaining:
        print(f"Aprovados={saved}. Pending file removido.")
    else:
        print(f"Aprovados={saved}. Restantes={len(remaining)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
