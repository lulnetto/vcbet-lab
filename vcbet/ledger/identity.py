from __future__ import annotations

import pandas as pd

from vcbet.ledger.schema import normalize_ledger_schema


def _norm_identity(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def _norm_line(value) -> str:
    if pd.isna(value) or value == "":
        return ""
    try:
        return f"{float(value):.2f}"
    except Exception:
        return _norm_identity(value)


def bet_identity_key(row: pd.Series | dict) -> tuple[str, ...]:
    return (
        _norm_identity(row.get("match_datetime")),
        _norm_identity(row.get("league")),
        _norm_identity(row.get("home_team")),
        _norm_identity(row.get("away_team")),
        _norm_identity(row.get("market_type")),
        _norm_identity(row.get("market_scope")),
        _norm_identity(row.get("side")),
        _norm_line(row.get("line")),
        _norm_identity(row.get("target_team_role") or "geral"),
        _norm_identity(row.get("target_team_name") or "geral"),
        _norm_identity(row.get("selection_raw")),
    )


def deduplicate_ledger_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove duplicatas de oportunidade, preservando a linha mais rica."""
    if df.empty:
        return normalize_ledger_schema(df), 0

    work = normalize_ledger_schema(df)

    def row_score(row: pd.Series) -> tuple[int, str]:
        executed = str(row.get("bet_executed", "")).strip().lower() in {"yes", "true", "1", "sim"}
        settlement = str(row.get("final_settlement_status", "")).strip().lower()
        settled = settlement not in {"", "pending", "nan", "none", "<na>"}
        manual = any(
            pd.notna(row.get(col)) and str(row.get(col)).strip().lower() not in {"", "nan", "<na>"}
            for col in ["manual_home_goals", "manual_away_goals", "manual_bet_status", "manual_settlement_status", "manual_odd_fechamento"]
        )
        created = str(row.get("created_at") or "")
        return (int(executed) * 100 + int(settled) * 50 + int(manual) * 25, created)

    work["__identity_key"] = work.apply(bet_identity_key, axis=1)
    keep_indices: list[int] = []
    for _, group in work.groupby("__identity_key", sort=False, dropna=False):
        if len(group) == 1:
            keep_indices.append(int(group.index[0]))
            continue
        best_idx = max(group.index, key=lambda idx: row_score(work.loc[idx]))
        keep_indices.append(int(best_idx))

    cleaned = work.loc[sorted(keep_indices)].drop(columns=["__identity_key"], errors="ignore")
    removed = len(work) - len(cleaned)
    return normalize_ledger_schema(cleaned), removed

