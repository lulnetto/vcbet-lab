from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_LEDGER_FILE = Path("data") / "history" / "bets_ledger.csv"

LEDGER_COLUMNS = [
    "bet_id",
    "run_id",
    "created_at",
    "settled_at",
    "league",
    "match_datetime",
    "home_team",
    "away_team",
    "match_name",
    "market_raw",
    "event_url",
    "market_type",
    "market_scope",
    "target_team_role",
    "target_team_name",
    "side",
    "line",
    "selection_raw",
    "odd_entrada",
    "odd_justa",
    "prob_model",
    "ev_percent",
    "confidence_score",
    "stake_units",
    "entry_reason",
    "risk_flags",
    "bet_executed",
    "executed_at",
    "odd_executada",
    "stake_units_executada",
    "execution_note",
    "auto_home_goals",
    "auto_away_goals",
    "auto_bet_status",
    "auto_settlement_status",
    "auto_odd_fechamento",
    "manual_home_goals",
    "manual_away_goals",
    "manual_bet_status",
    "manual_settlement_status",
    "manual_odd_fechamento",
    "final_home_goals",
    "final_away_goals",
    "final_bet_status",
    "final_settlement_status",
    "final_odd_fechamento",
    "settlement_source",
    "settlement_confidence",
    "settlement_note",
    "override_reason",
    "override_updated_at",
    "result_units_model",
    "result_units_real",
]


def _empty_value():
    return pd.NA


def ensure_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    path = Path(ledger_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pd.DataFrame(columns=LEDGER_COLUMNS).to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def load_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> pd.DataFrame:
    path = ensure_ledger(ledger_file)
    df = pd.read_csv(path, sep=";")
    for column in LEDGER_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df[LEDGER_COLUMNS].copy()


def save_ledger(df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    path = ensure_ledger(ledger_file)
    for column in LEDGER_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    df[LEDGER_COLUMNS].to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def _pick_to_ledger_row(pick: pd.Series) -> dict:
    return {
        "bet_id": pick["bet_id"],
        "run_id": pick["run_id"],
        "created_at": pick["generated_at"],
        "settled_at": pd.NA,
        "league": pick["league"],
        "match_datetime": pick["match_datetime"],
        "home_team": pick["home_team"],
        "away_team": pick["away_team"],
        "match_name": pick["match_name"],
        "market_raw": pick.get("market_raw"),
        "event_url": pick.get("event_url"),
        "market_type": pick["market_type"],
        "market_scope": pick["market_scope"],
        "target_team_role": pick.get("target_team_role", "geral"),
        "target_team_name": pick.get("target_team_name", "geral"),
        "side": pick.get("side"),
        "line": pick.get("line"),
        "selection_raw": pick["selection_raw"],
        "odd_entrada": pick["odd_entrada"],
        "odd_justa": pick.get("odd_justa"),
        "prob_model": pick.get("prob_model"),
        "ev_percent": pick.get("ev_percent"),
        "confidence_score": pick.get("confidence_score"),
        "stake_units": pick.get("stake_units"),
        "entry_reason": pick.get("entry_reason"),
        "risk_flags": pick.get("risk_flags"),
        "bet_executed": "no",
        "executed_at": pd.NA,
        "odd_executada": pd.NA,
        "stake_units_executada": pd.NA,
        "execution_note": pd.NA,
        "auto_home_goals": pd.NA,
        "auto_away_goals": pd.NA,
        "auto_bet_status": "open",
        "auto_settlement_status": "pending",
        "auto_odd_fechamento": pd.NA,
        "manual_home_goals": pd.NA,
        "manual_away_goals": pd.NA,
        "manual_bet_status": pd.NA,
        "manual_settlement_status": pd.NA,
        "manual_odd_fechamento": pd.NA,
        "final_home_goals": pd.NA,
        "final_away_goals": pd.NA,
        "final_bet_status": "open",
        "final_settlement_status": "pending",
        "final_odd_fechamento": pd.NA,
        "settlement_source": pd.NA,
        "settlement_confidence": pd.NA,
        "settlement_note": pd.NA,
        "override_reason": pd.NA,
        "override_updated_at": pd.NA,
        "result_units_model": pd.NA,
        "result_units_real": pd.NA,
    }


def append_new_picks_to_ledger(picks_df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> tuple[Path, int, int]:
    path = ensure_ledger(ledger_file)
    ledger_df = load_ledger(path)
    if picks_df.empty:
        save_ledger(ledger_df, path)
        return path, 0, len(ledger_df)

    existing_ids = set(ledger_df["bet_id"].dropna().astype(str).tolist())
    new_rows = []
    for _, row in picks_df.iterrows():
        bet_id = str(row["bet_id"])
        if bet_id in existing_ids:
            continue
        new_rows.append(_pick_to_ledger_row(row))
        existing_ids.add(bet_id)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        if ledger_df.empty:
            ledger_df = new_df.reindex(columns=LEDGER_COLUMNS)
        else:
            ledger_df = pd.concat([ledger_df, new_df.reindex(columns=LEDGER_COLUMNS)], ignore_index=True)

    save_ledger(ledger_df, path)
    return path, len(new_rows), len(ledger_df)
