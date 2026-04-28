from __future__ import annotations

from typing import Any

import pandas as pd


ODDS_CRITICAL_REQUIRED_COLUMNS = {
    "league",
    "match_name",
    "home_team",
    "away_team",
    "odd",
    "selection_raw",
}

ODDS_MODEL_REQUIRED_COLUMNS = {
    "market_type",
    "market_scope",
    "normalized_status",
}

ODDS_REQUIRED_COLUMNS = ODDS_CRITICAL_REQUIRED_COLUMNS

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


def _critical_invalid_rows(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    checks = []
    for col in ODDS_CRITICAL_REQUIRED_COLUMNS:
        if col in df.columns:
            if col == "odd":
                try:
                    numeric = pd.to_numeric(df[col], errors="coerce")
                    checks.append(numeric.isna() | (numeric <= 0))
                except Exception:
                    checks.append(pd.Series([True] * len(df), index=df.index))
            else:
                checks.append(df[col].isna() | (df[col].astype(str).str.strip() == ""))
        else:
            checks.append(pd.Series([True] * len(df), index=df.index))
    result = checks[0]
    for c in checks[1:]:
        result = result | c
    return result


def _unsupported_market_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    if "normalized_status" not in df.columns:
        return 0.0
    critical = _critical_invalid_rows(df)
    non_critical = ~critical
    unsupported = non_critical & (df["normalized_status"] != "ok")
    return float(unsupported.sum() / len(df))


def _model_eligible_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    if "normalized_status" not in df.columns:
        return 0.0
    ok = (df["normalized_status"] == "ok").sum()
    return float(ok / len(df))


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
    odds_manifest: dict | None = None,
    max_critical_invalid_rate: float = 0.10,
    min_raw_selections_per_event: int = 10,
    max_event_failure_rate: float = 0.25,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

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

    # Manifest-based fatal checks
    if odds_manifest is not None:
        manifest_status = str(odds_manifest.get("status", "")).lower()
        if manifest_status in ("failed", "partial", "error"):
            errors.append({"code": "odds_manifest_status_bad", "message": f"Odds collection manifest status is {manifest_status}."})
        total_stats = odds_manifest.get("totals", {})
        events_found = total_stats.get("events_found", 0)
        events_failed = total_stats.get("events_failed", 0)
        if events_found > 0:
            event_failure_rate = events_failed / events_found
            if event_failure_rate > max_event_failure_rate:
                errors.append({"code": "odds_event_failure_rate_high", "message": f"Event failure rate {event_failure_rate:.2%} exceeds threshold {max_event_failure_rate:.2%}."})
        events_success = total_stats.get("events_success", 0)
        raw_selections = total_stats.get("raw_selections_seen", 0)
        if events_success > 0:
            avg_raw = raw_selections / events_success
            if avg_raw < min_raw_selections_per_event:
                errors.append({"code": "odds_avg_raw_selections_low", "message": f"Avg raw selections per event {avg_raw:.1f} below threshold {min_raw_selections_per_event}."})
        normalized_ok = total_stats.get("normalized_ok_rows", 0)
        if normalized_ok == 0 and raw_selections > 0:
            errors.append({"code": "odds_no_supported_markets_after_normalization", "message": "No normalized ok rows despite raw selections existing."})

    # DataFrame-based critical invalid rate
    odds_critical = _critical_invalid_rows(df_odds)
    critical_invalid_rate = float(odds_critical.sum() / len(df_odds)) if not df_odds.empty else 0.0
    if critical_invalid_rate > max_critical_invalid_rate:
        errors.append({"code": "odds_critical_invalid_rate_high", "message": f"Critical invalid rate {critical_invalid_rate:.2%} exceeds threshold {max_critical_invalid_rate:.2%}."})

    # xG failure rate
    xg_failure = _xg_failure_rate(df_xg)
    if xg_failure > max_invalid_snapshot_row_rate:
        errors.append({"code": "xg_failure_rate_high", "message": f"xG failure rate {xg_failure:.2%} exceeds threshold {max_invalid_snapshot_row_rate:.2%}."})

    # Provenance
    if not df_odds.empty and not _has_provenance(df_odds):
        errors.append({"code": "odds_missing_provenance", "message": "Odds snapshot lacks run_id or collected_at."})
    if not df_xg.empty and not _has_provenance(df_xg):
        errors.append({"code": "xg_missing_provenance", "message": "xG snapshot lacks run_id or collected_at."})

    # Warnings (non-fatal)
    unsupported_rate = _unsupported_market_rate(df_odds)
    if unsupported_rate > 0.5:
        warnings.append({"code": "unsupported_market_rate_high", "message": f"Unsupported market rate {unsupported_rate:.2%}."})
    eligible_rate = _model_eligible_rate(df_odds)
    if eligible_rate < 0.1 and not df_odds.empty:
        warnings.append({"code": "model_eligible_rate_low", "message": f"Model eligible rate {eligible_rate:.2%}."})
    if not df_odds.empty and "market_scope" in df_odds.columns:
        ok_rows = df_odds[df_odds["normalized_status"] == "ok"] if "normalized_status" in df_odds.columns else df_odds
        if not ok_rows.empty and ok_rows[ok_rows["market_scope"] == "full_time"].empty:
            warnings.append({"code": "no_full_time_markets", "message": "No full_time markets after normalization."})
        elif "normalized_status" in df_odds.columns and ok_rows.empty:
            warnings.append({"code": "no_eligible_markets", "message": "No rows with normalized_status == 'ok'."})

    is_valid = not errors if require_snapshot_health_ok else True

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "odds_critical_invalid_rate": critical_invalid_rate,
        "unsupported_market_rate": unsupported_rate,
        "model_eligible_rate": eligible_rate,
        "xg_failure_rate": xg_failure,
        "odds_missing_columns": odds_missing,
        "xg_missing_columns": xg_missing,
    }
