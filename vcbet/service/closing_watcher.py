from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from vcbet.collectors.closing_odds_collector import BetanoClosingOddsCollector, market_row_matches, parse_match_datetime
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, load_ledger, save_ledger


CLOSING_FIELDS = [
    "closing_odd",
    "closing_bookmaker",
    "closing_snapshot_time",
    "closing_source",
    "closing_update_status",
    "closing_update_error",
]


def minutes_before_from_env(default: int = 60) -> int:
    raw = os.getenv("VCBET_CLOSING_ODDS_MINUTES_BEFORE", str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _has_value(value: Any) -> bool:
    return value is not None and pd.notna(value) and str(value).strip() != ""


def _is_unsettled(row: pd.Series) -> bool:
    bet_status = str(row.get("final_bet_status", "")).strip().lower()
    settlement_status = str(row.get("final_settlement_status", "")).strip().lower()
    if bet_status in {"settled", "voided", "cancelled", "postponed", "unmatched"}:
        return False
    return settlement_status not in {"win", "loss", "half_win", "half_loss", "push", "void"}


def eligible_rows(
    df: pd.DataFrame,
    *,
    now: datetime | None = None,
    minutes_before: int = 60,
    allow_past_minutes: int = 10,
    all_pending: bool = False,
    bet_ids: list[str] | None = None,
) -> pd.DataFrame:
    now = now or datetime.now()
    bet_id_set = {str(item).strip() for item in bet_ids or [] if str(item).strip()}
    lower_bound = now - timedelta(minutes=allow_past_minutes)
    upper_bound = now + timedelta(minutes=minutes_before)
    rows = []
    for idx, row in df.iterrows():
        if bet_id_set and str(row.get("bet_id", "")).strip() not in bet_id_set:
            continue
        if not _is_unsettled(row):
            continue
        if _has_value(row.get("closing_odd")) or _has_value(row.get("closing_snapshot_time")):
            continue
        if not _has_value(row.get("event_url")):
            continue
        if all_pending:
            rows.append(idx)
            continue
        match_dt = parse_match_datetime(row.get("match_datetime"))
        if match_dt is not None and lower_bound <= match_dt <= upper_bound:
            rows.append(idx)
    return df.loc[rows].copy()


def update_closing_odds_once(
    ledger_file: str | Path = DEFAULT_LEDGER_FILE,
    *,
    minutes_before: int | None = None,
    allow_past_minutes: int = 10,
    all_pending: bool = False,
    bet_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    ledger_path = Path(ledger_file)
    df = load_ledger(ledger_path)
    minutes_before = minutes_before if minutes_before is not None else minutes_before_from_env()
    targets = eligible_rows(
        df,
        minutes_before=minutes_before,
        allow_past_minutes=allow_past_minutes,
        all_pending=all_pending,
        bet_ids=bet_ids,
    )
    if targets.empty:
        if not dry_run:
            save_ledger(df, ledger_path)
        return {"ledger_file": str(ledger_path), "eligible": 0, "updated": 0, "fetched_urls": 0, "failed_urls": 0, "dry_run": dry_run}

    collector = BetanoClosingOddsCollector()
    market_cache: dict[str, list[dict[str, Any]]] = {}
    updated = 0
    failed_urls = 0

    for idx, row in targets.iterrows():
        event_url = str(row.get("event_url")).strip()
        if event_url not in market_cache:
            try:
                market_cache[event_url] = collector.fetch_market_rows(event_url)
            except Exception as exc:
                market_cache[event_url] = []
                failed_urls += 1
                df.at[idx, "closing_update_status"] = "fetch_failed"
                df.at[idx, "closing_update_error"] = str(exc)[:300]
                continue

        match = next((market_row for market_row in market_cache[event_url] if market_row_matches(row, market_row)), None)
        if not match:
            df.at[idx, "closing_update_status"] = "market_not_found"
            df.at[idx, "closing_update_error"] = "matching market/selection not found for event_url"
            continue

        df.at[idx, "closing_odd"] = float(match["odd"])
        df.at[idx, "closing_bookmaker"] = "betano"
        df.at[idx, "closing_snapshot_time"] = datetime.now().isoformat(timespec="seconds")
        df.at[idx, "closing_source"] = event_url
        df.at[idx, "closing_update_status"] = "updated"
        df.at[idx, "closing_update_error"] = ""
        updated += 1

    if not dry_run:
        save_ledger(df, ledger_path)

    return {
        "ledger_file": str(ledger_path),
        "eligible": int(len(targets)),
        "updated": updated,
        "fetched_urls": len(market_cache),
        "failed_urls": failed_urls,
        "dry_run": dry_run,
    }
