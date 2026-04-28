from __future__ import annotations

from typing import Any

import pandas as pd


ODDS_REQUIRED_COLUMNS = {
    "league",
    "match_name",
    "home_team",
    "away_team",
    "market_type",
    "market_scope",
    "odd",
    "selection_raw",
}

XG_REQUIRED_COLUMNS = {
    "team_name",
    "league",
    "xg",
}


def _missing_columns(df: pd.DataFrame, required: set[str]) -> list[str]:
    return [col for col in required if col not in df.columns]


def _invalid_rate(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    invalid = series.isna() | (series.astype(str).str.strip() == "")
    return float(invalid.sum() / len(series))


def _odds_failure_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 1.0
    if "normalized_status" in df.columns:
        not_ok = (df["normalized_status"] != "ok").sum()
        return float(not_ok / len(df))
    return 0.0


def _xg_failure_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 1.0
    core_cols = [c for c in ("team_name", "league", "xg") if c in df.columns]
    if not core_cols:
        return 1.0
    missing_any = df[core_cols].isna().any(axis=1)
    return float(missing_any.sum() / len(df))


def _has_provenance(df: pd.DataFrame) -> bool:
    return "run_id" in df.columns or "collected_at" in df.columns


def validate_snapshot_health(
    df_odds: pd.DataFrame,
    df_xg: pd.DataFrame,
    *,
    max_invalid_snapshot_row_rate: float = 0.25,
    require_snapshot_health_ok: bool = True,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    # Empty checks
    if df_odds.empty:
        errors.append({"code": "empty_odds_snapshot", "message": "Odds snapshot has zero rows."})
    if df_xg.empty:
        errors.append({"code": "empty_xg_snapshot", "message": "xG snapshot has zero rows."})

    # Required columns
    odds_missing = _missing_columns(df_odds, ODDS_REQUIRED_COLUMNS)
    if odds_missing:
        errors.append({"code": "odds_missing_required_columns", "message": f"Missing: {', '.join(odds_missing)}"})
    xg_missing = _missing_columns(df_xg, XG_REQUIRED_COLUMNS)
    if xg_missing:
        errors.append({"code": "xg_missing_required_columns", "message": f"Missing: {', '.join(xg_missing)}"})

    # Failure rates
    odds_failure = _odds_failure_rate(df_odds)
    xg_failure = _xg_failure_rate(df_xg)
    if odds_failure > max_invalid_snapshot_row_rate:
        errors.append({"code": "odds_failure_rate_high", "message": f"Odds failure rate {odds_failure:.2%} exceeds threshold {max_invalid_snapshot_row_rate:.2%}."})
    if xg_failure > max_invalid_snapshot_row_rate:
        errors.append({"code": "xg_failure_rate_high", "message": f"xG failure rate {xg_failure:.2%} exceeds threshold {max_invalid_snapshot_row_rate:.2%}."})

    # Provenance
    if not df_odds.empty and not _has_provenance(df_odds):
        errors.append({"code": "odds_missing_provenance", "message": "Odds snapshot lacks run_id or collected_at."})
    if not df_xg.empty and not _has_provenance(df_xg):
        errors.append({"code": "xg_missing_provenance", "message": "xG snapshot lacks run_id or collected_at."})

    # Active leagues / eligible markets
    if not df_odds.empty and "normalized_status" in df_odds.columns:
        ok_rows = df_odds[df_odds["normalized_status"] == "ok"]
        if ok_rows.empty:
            errors.append({"code": "no_eligible_markets", "message": "No rows with normalized_status == 'ok'."})
        elif "market_scope" in ok_rows.columns:
            full_time = ok_rows[ok_rows["market_scope"] == "full_time"]
            if full_time.empty:
                errors.append({"code": "no_full_time_markets", "message": "No full_time markets after normalization."})

    is_valid = not errors if require_snapshot_health_ok else True

    return {
        "is_valid": is_valid,
        "errors": errors,
        "odds_failure_rate": odds_failure,
        "xg_failure_rate": xg_failure,
        "odds_missing_columns": odds_missing,
        "xg_missing_columns": xg_missing,
    }
