#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE
from vcbet.service.closing_watcher import update_closing_odds_once


def main() -> int:
    parser = argparse.ArgumentParser(description="Atualiza closing odds em campos dedicados usando event_url.")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE))
    parser.add_argument("--window-minutes", type=int, default=None, help="Minutos antes do kickoff; usa VCBET_CLOSING_ODDS_MINUTES_BEFORE ou 60 se omitido.")
    parser.add_argument("--allow-past-minutes", type=int, default=10)
    parser.add_argument("--all-pending", action="store_true")
    parser.add_argument("--bet-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = update_closing_odds_once(
        ledger_file=args.ledger_file,
        minutes_before=args.window_minutes,
        allow_past_minutes=args.allow_past_minutes,
        all_pending=args.all_pending,
        bet_ids=args.bet_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
