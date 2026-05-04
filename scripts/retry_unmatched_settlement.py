#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from vcbet.collectors.results_collector import (
    MatchResult,
    MatchTarget,
    build_targets,
    collect_results_sofascore_api,
    collect_results_sofascore_auto,
    collect_results_sofascore_browser,
    load_ledger,
    parse_datetime,
)
from vcbet.core.ledger_manager import normalize_sofascore_event_id, update_ledger
from vcbet.core.run_utils import now_str
from vcbet.paths import DEFAULT_OVERRIDES_FILE, DEFAULT_RESULTS_DEBUG_DIR
from vcbet.settlement.settlement_engine import settle_ledger


DEFAULT_RETRY_RESULTS_FILE = Path("data/results/results_unmatched_retry.csv")

RESULT_FIELDNAMES = [
    "bet_id",
    "league",
    "match_name",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "bet_status",
    "settlement_source",
    "settlement_confidence",
    "settlement_note",
    "source_url",
    "matched_via",
    "status_raw",
    "source_event_id",
    "match_datetime",
]

TELEMETRY_COLUMNS = [
    "match_resolution_status",
    "match_resolution_reason",
    "match_resolution_attempts",
    "last_match_resolution_attempt_at",
    "resolved_result_provider",
    "resolved_event_id",
    "resolved_event_url",
]


def _clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _clean_status(value: Any) -> str:
    return _clean_text(value).lower()


def _is_missing(value: Any) -> bool:
    return _clean_text(value) == ""


def _first_present(*values: Any, default: Any = "") -> Any:
    for value in values:
        if not _is_missing(value):
            return value
    return default


def _safe_attempts(value: Any) -> int:
    if _is_missing(value):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _target_key_from_values(league: Any, match_name: Any, home_team: Any, away_team: Any) -> tuple[str, str, str, str]:
    return (
        _clean_text(league),
        _clean_text(match_name),
        _clean_text(home_team),
        _clean_text(away_team),
    )


def _target_key(target: MatchTarget) -> tuple[str, str, str, str]:
    return _target_key_from_values(target.league, target.match_name, target.home_team, target.away_team)


def _unmatched_target_mask(df: pd.DataFrame, date: str | None) -> pd.Series:
    if "final_bet_status" not in df.columns:
        return pd.Series(False, index=df.index)

    mask = df["final_bet_status"].astype(str).str.strip().str.lower().eq("unmatched")
    if not date:
        return mask

    requested_date = datetime.strptime(date, "%Y-%m-%d").date()
    if "match_datetime" not in df.columns:
        return pd.Series(False, index=df.index)

    match_dates = df["match_datetime"].apply(parse_datetime)
    return mask & match_dates.apply(lambda value: value is not None and value.date() == requested_date)


def _target_rows_by_key(target_rows: pd.DataFrame) -> dict[tuple[str, str, str, str], list[pd.Series]]:
    rows: dict[tuple[str, str, str, str], list[pd.Series]] = {}
    for _, row in target_rows.iterrows():
        key = _target_key_from_values(
            row.get("league"),
            row.get("match_name"),
            row.get("home_team"),
            row.get("away_team"),
        )
        rows.setdefault(key, []).append(row)
    return rows


def _result_row_for_bet(result: MatchResult, bet_id: str) -> dict[str, Any]:
    row = {field: getattr(result, field, "") for field in RESULT_FIELDNAMES if field != "bet_id"}
    row["bet_id"] = bet_id
    return {field: row.get(field, "") for field in RESULT_FIELDNAMES}


def expand_results_for_targets(
    targets: list[MatchTarget],
    results: list[MatchResult],
    target_rows: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows_by_key = _target_rows_by_key(target_rows)
    expanded: list[dict[str, Any]] = []
    for target, result in zip(targets, results):
        for row in rows_by_key.get(_target_key(target), []):
            bet_id = _clean_text(row.get("bet_id"))
            if not bet_id:
                continue
            expanded.append(_result_row_for_bet(result, bet_id))
    return expanded


def save_retry_results_csv(rows: list[dict[str, Any]], output_file: str | Path) -> Path:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDNAMES, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return path


def collect_results(
    targets: list[MatchTarget],
    *,
    source: str,
    debug: bool,
    max_pages: int,
) -> list[MatchResult]:
    debug_dir = Path(DEFAULT_RESULTS_DEBUG_DIR) / "unmatched_retry" if debug else None
    if source == "browser":
        return collect_results_sofascore_browser(
            targets=targets,
            debug=debug,
            debug_dir=debug_dir,
            max_pages=max_pages,
        )
    if source == "api":
        return collect_results_sofascore_api(
            targets=targets,
            debug=debug,
            debug_dir=debug_dir,
            max_pages=max_pages,
        )
    return collect_results_sofascore_auto(
        targets=targets,
        debug=debug,
        debug_dir=debug_dir,
        max_pages=max_pages,
    )


def _ensure_telemetry_columns(df: pd.DataFrame) -> pd.DataFrame:
    updated = df.copy()
    for column in TELEMETRY_COLUMNS:
        if column not in updated.columns:
            updated[column] = pd.NA
        updated[column] = updated[column].astype("object")
    return updated


def mark_retry_started(ledger_file: str | Path, bet_ids: set[str], attempted_at: str) -> int:
    if not bet_ids:
        return 0

    def mutate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        updated = _ensure_telemetry_columns(df)
        mask = updated["bet_id"].astype(str).str.strip().isin(bet_ids)
        for idx in updated.index[mask]:
            updated.at[idx, "match_resolution_attempts"] = _safe_attempts(updated.at[idx, "match_resolution_attempts"]) + 1
            updated.at[idx, "last_match_resolution_attempt_at"] = attempted_at
            updated.at[idx, "match_resolution_status"] = "pending"
        return updated, int(mask.sum())

    _path, count = update_ledger(ledger_file, mutate)
    return count


def _result_rows_by_bet_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_bet_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        bet_id = _clean_text(row.get("bet_id"))
        if bet_id:
            by_bet_id[bet_id] = row
    return by_bet_id


def finalize_retry_telemetry(
    ledger_file: str | Path,
    bet_ids: set[str],
    result_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    if not bet_ids:
        return 0, 0

    results_by_bet_id = _result_rows_by_bet_id(result_rows)

    def mutate(df: pd.DataFrame) -> tuple[pd.DataFrame, tuple[int, int]]:
        updated = _ensure_telemetry_columns(df)
        mask = updated["bet_id"].astype(str).str.strip().isin(bet_ids)
        settled_after = 0
        still_unmatched = 0

        for idx in updated.index[mask]:
            bet_id = _clean_text(updated.at[idx, "bet_id"])
            result_row = results_by_bet_id.get(bet_id, {})
            final_status = _clean_status(updated.at[idx, "final_bet_status"])
            settlement_note = _clean_text(updated.at[idx, "settlement_note"])
            source_event_id = normalize_sofascore_event_id(
                _first_present(
                    updated.at[idx, "sofascore_event_id"],
                    result_row.get("source_event_id"),
                    default="",
                )
            )
            matched_open = (
                final_status == "open"
                and _clean_status(result_row.get("bet_status")) == "open"
                and _clean_status(result_row.get("settlement_confidence")) == "high"
                and bool(source_event_id)
            )

            if final_status == "settled" or matched_open:
                if final_status == "settled":
                    settled_after += 1
                updated.at[idx, "match_resolution_status"] = "resolved"
                updated.at[idx, "match_resolution_reason"] = pd.NA
                updated.at[idx, "resolved_result_provider"] = _first_present(
                    updated.at[idx, "settlement_source"],
                    result_row.get("settlement_source"),
                    default=pd.NA,
                )
                updated.at[idx, "resolved_event_id"] = source_event_id if source_event_id else pd.NA
                updated.at[idx, "resolved_event_url"] = _first_present(result_row.get("source_url"), default=pd.NA)
                continue

            updated.at[idx, "match_resolution_status"] = "pending"
            updated.at[idx, "resolved_result_provider"] = pd.NA
            updated.at[idx, "resolved_event_id"] = pd.NA
            updated.at[idx, "resolved_event_url"] = pd.NA
            if final_status == "unmatched":
                still_unmatched += 1
                updated.at[idx, "match_resolution_reason"] = settlement_note or "NO_PROVIDER_MATCH"
            else:
                updated.at[idx, "match_resolution_reason"] = settlement_note or f"FINAL_STATUS_{final_status.upper() or 'PENDING'}"

        return updated, (settled_after, still_unmatched)

    _path, counts = update_ledger(ledger_file, mutate)
    return counts


def print_summary(
    *,
    unmatched_before: int,
    targets: int,
    results_collected: int,
    settled_after: int,
    still_unmatched: int,
    results_file: Path,
    ledger_file: str | Path,
) -> None:
    resolved_delta = targets - still_unmatched
    print(f"unmatched_before={unmatched_before}")
    print(f"targets={targets}")
    print(f"results_collected={results_collected}")
    print(f"settled_after={settled_after}")
    print(f"still_unmatched={still_unmatched}")
    print(f"resolved_delta={resolved_delta}")
    print(f"results_file={results_file}")
    print(f"ledger_file={ledger_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprocessa entradas unmatched usando o fluxo results_collector -> settlement_engine.")
    parser.add_argument("--ledger-file", required=True, help="Caminho do bets_ledger.csv")
    parser.add_argument("--results-file", default=str(DEFAULT_RETRY_RESULTS_FILE), help="CSV gerado com os resultados do retry")
    parser.add_argument("--date", help="Filtra por match_datetime no formato YYYY-MM-DD")
    parser.add_argument("--max-pages", type=int, default=12, help="Quantidade máxima de páginas events/last/{page} por liga")
    parser.add_argument("--source", choices=["auto", "browser", "api"], default="auto", help="Fonte de coleta do Sofascore")
    parser.add_argument("--debug", action="store_true", help="Exibe logs detalhados")
    parser.add_argument("--dry-run", action="store_true", help="Coleta e salva results sem alterar o ledger")
    parser.add_argument("--no-overrides", action="store_true", help="Ignora overrides manuais nesta execução")
    parser.add_argument("--overrides-file", default=str(DEFAULT_OVERRIDES_FILE), help="CSV de overrides manuais")
    args = parser.parse_args()

    df = load_ledger(args.ledger_file)
    unmatched_before = int(df["final_bet_status"].astype(str).str.strip().str.lower().eq("unmatched").sum())
    target_mask = _unmatched_target_mask(df, args.date)
    target_rows = df.loc[target_mask].copy()
    target_bet_ids = {_clean_text(value) for value in target_rows.get("bet_id", pd.Series(dtype="object")).tolist()}
    target_bet_ids.discard("")

    targets = build_targets(
        df,
        only_ready=False,
        grace_minutes=0,
        only_unmatched=True,
        date=args.date,
    )

    if args.debug:
        print(f"[DEBUG] unmatched_before={unmatched_before}")
        print(f"[DEBUG] target_entries={len(target_rows)}")
        print(f"[DEBUG] collection_targets={len(targets)}")
        print(f"[DEBUG] source={args.source}")
        print(f"[DEBUG] max_pages={args.max_pages}")

    results = collect_results(targets, source=args.source, debug=args.debug, max_pages=args.max_pages) if targets else []
    expanded_rows = expand_results_for_targets(targets, results, target_rows) if results else []
    results_path = save_retry_results_csv(expanded_rows, args.results_file)

    if args.dry_run or not target_bet_ids:
        print_summary(
            unmatched_before=unmatched_before,
            targets=len(target_rows),
            results_collected=len(expanded_rows),
            settled_after=0,
            still_unmatched=len(target_rows),
            results_file=results_path,
            ledger_file=args.ledger_file,
        )
        return 0

    attempted_at = now_str()
    mark_retry_started(args.ledger_file, target_bet_ids, attempted_at)
    settle_ledger(
        ledger_file=args.ledger_file,
        results_file=results_path,
        overrides_file=None if args.no_overrides else args.overrides_file,
    )
    settled_after, still_unmatched = finalize_retry_telemetry(args.ledger_file, target_bet_ids, expanded_rows)

    print_summary(
        unmatched_before=unmatched_before,
        targets=len(target_rows),
        results_collected=len(expanded_rows),
        settled_after=settled_after,
        still_unmatched=still_unmatched,
        results_file=results_path,
        ledger_file=args.ledger_file,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
