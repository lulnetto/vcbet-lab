from __future__ import annotations

from pathlib import Path
from typing import Any

import csv
import pandas as pd

SETTLED_BET_STATUSES = {"settled", "voided", "postponed"}


def _safe_numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def _read_csv_auto(path: Path) -> pd.DataFrame:
    sample = path.read_text(encoding="utf-8", errors="ignore")[:8192]
    delimiters = [",", ";", "\t", "|"]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=delimiters)
        sep = dialect.delimiter
    except Exception:
        first_line = sample.splitlines()[0] if sample else ""
        counts = {d: first_line.count(d) for d in delimiters}
        sep = max(counts, key=counts.get) if any(counts.values()) else ";"

    df = pd.read_csv(path, sep=sep)

    if len(df.columns) == 1:
        only = str(df.columns[0])
        for candidate in [";", ",", "\t", "|"]:
            if candidate in only:
                retry = pd.read_csv(path, sep=candidate)
                if len(retry.columns) > 1:
                    return retry
    return df


def load_ledger(ledger_file: str | Path) -> pd.DataFrame:
    path = Path(ledger_file)
    if not path.exists():
        raise FileNotFoundError(f"ledger não encontrado: {path}")
    df = _read_csv_auto(path)
    for col in [
        "created_at",
        "executed_at",
        "closing_collected_at",
        "override_updated_at",
        "settled_at",
        "match_datetime",
    ]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def apply_filters(
    df: pd.DataFrame,
    *,
    run_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    league: str | None = None,
    market_type: str | None = None,
    only_executed: bool = False,
    only_settled: bool = False,
) -> pd.DataFrame:
    out = df.copy()
    if run_id:
        out = out[out.get("run_id", pd.Series(index=out.index)).astype(str) == str(run_id)]
    if league:
        out = out[out.get("league", pd.Series(index=out.index)).astype(str) == str(league)]
    if market_type:
        out = out[out.get("market_type", pd.Series(index=out.index)).astype(str) == str(market_type)]
    if date_from:
        dt = pd.to_datetime(date_from, errors="coerce")
        if pd.notna(dt):
            if "match_datetime" in out.columns:
                out = out[out["match_datetime"] >= dt]
            elif "created_at" in out.columns:
                out = out[out["created_at"] >= dt]
    if date_to:
        dt = pd.to_datetime(date_to, errors="coerce")
        if pd.notna(dt):
            if "match_datetime" in out.columns:
                out = out[out["match_datetime"] <= dt]
            elif "created_at" in out.columns:
                out = out[out["created_at"] <= dt]
    if only_executed and "bet_executed" in out.columns:
        out = out[out["bet_executed"].astype(str).str.lower() == "yes"]
    if only_settled and "final_bet_status" in out.columns:
        out = out[out["final_bet_status"].astype(str).isin(SETTLED_BET_STATUSES)]
    return out


def _split_flags(series: pd.Series | None, index: pd.Index) -> pd.DataFrame:
    raw = series if series is not None else pd.Series(index=index, dtype="object")
    rows: list[dict[str, Any]] = []
    for bet_id, value in raw.fillna("SEM_FLAG").astype(str).items():
        parts = [p.strip() for p in value.split("|") if p.strip()]
        if not parts:
            parts = ["SEM_FLAG"]
        for part in parts:
            rows.append({"bet_id": bet_id, "risk_flag": part})
    return pd.DataFrame(rows)


def _bucket_odds(series: pd.Series) -> pd.Series:
    bins = [0, 1.5, 1.8, 2.0, 2.2, 2.5, 3.0, 100]
    labels = ["<=1.50", "1.51-1.80", "1.81-2.00", "2.01-2.20", "2.21-2.50", "2.51-3.00", "3.01+"]
    return pd.cut(series, bins=bins, labels=labels, include_lowest=True, right=True)


def _bucket_stake(series: pd.Series) -> pd.Series:
    bins = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 100]
    labels = ["<=0.5u", "0.51-1.0u", "1.01-1.5u", "1.51-2.0u", "2.01-3.0u", "3.01u+"]
    return pd.cut(series, bins=bins, labels=labels, include_lowest=True, right=True)


def _aggregate_performance(df: pd.DataFrame, group_col: str) -> list[dict[str, Any]]:
    if df.empty or group_col not in df.columns:
        return []
    work = df.copy()
    work["stake_units"] = _safe_numeric(work, "stake_units").fillna(0)
    work["result_units_model"] = _safe_numeric(work, "result_units_model").fillna(0)
    work["result_units_real"] = _safe_numeric(work, "result_units_real").fillna(0)
    work["odd_entrada"] = _safe_numeric(work, "odd_entrada")
    work["ev_percent"] = _safe_numeric(work, "ev_percent")

    group_values = work[group_col]
    if pd.api.types.is_categorical_dtype(group_values):
        group_values = group_values.astype(object)
    work[group_col] = group_values.where(group_values.notna(), "NA")

    grouped = (
        work.groupby(group_col, dropna=False, observed=False)
        .agg(
            picks=("bet_id", "count"),
            stake=("stake_units", "sum"),
            units_model=("result_units_model", "sum"),
            units_real=("result_units_real", "sum"),
            avg_odd=("odd_entrada", "mean"),
            avg_ev=("ev_percent", "mean"),
        )
        .reset_index()
    )
    grouped["roi_model_percent"] = grouped.apply(
        lambda r: (r["units_model"] / r["stake"] * 100) if r["stake"] else 0.0,
        axis=1,
    )
    grouped["yield_model_percent"] = grouped["roi_model_percent"]
    grouped = grouped.rename(columns={group_col: "bucket"})
    grouped["bucket"] = grouped["bucket"].astype(str)
    return grouped.sort_values(["units_model", "picks"], ascending=[False, False]).to_dict(orient="records")


def _recent_entries(df: pd.DataFrame, limit: int = 100) -> list[dict[str, Any]]:
    recent_entries = df.copy()
    if "match_datetime" in recent_entries.columns:
        recent_entries = recent_entries.sort_values("match_datetime", ascending=True, na_position="last")
    elif "created_at" in recent_entries.columns:
        recent_entries = recent_entries.sort_values("created_at", ascending=False)
    recent_entries = recent_entries.head(limit).copy()
    recent_cols = [
        "bet_id",
        "match_datetime",
        "created_at",
        "run_id",
        "config_name",
        "league",
        "match_name",
        "market_type",
        "selection_raw",
        "line",
        "odd_entrada",
        "ev_percent",
        "stake_units",
        "bet_executed",
        "final_bet_status",
        "final_settlement_status",
        "result_units_model",
        "result_units_real",
        "risk_flags",
    ]
    recent_cols = [c for c in recent_cols if c in recent_entries.columns]
    recent_entries = recent_entries[recent_cols].fillna("")
    for dt_col in ["match_datetime", "created_at"]:
        if dt_col in recent_entries.columns:
            recent_entries[dt_col] = recent_entries[dt_col].astype(str)
    return recent_entries.to_dict(orient="records")


def build_dashboard_payload(df: pd.DataFrame, entries_limit: int = 100) -> dict[str, Any]:
    total = len(df)
    open_df = df[df.get("final_bet_status", pd.Series(index=df.index)).astype(str) == "open"].copy()
    settled = df[df.get("final_bet_status", pd.Series(index=df.index)).astype(str).isin(SETTLED_BET_STATUSES)].copy()
    executed = df[df.get("bet_executed", pd.Series(index=df.index)).astype(str).str.lower() == "yes"].copy()
    executed_settled = executed[executed.get("final_bet_status", pd.Series(index=executed.index)).astype(str).isin(SETTLED_BET_STATUSES)].copy()

    model_stake = _safe_numeric(settled, "stake_units").fillna(0).sum()
    model_units = _safe_numeric(settled, "result_units_model").fillna(0).sum()
    model_roi = (model_units / model_stake * 100) if model_stake else 0.0

    real_stake = _safe_numeric(executed_settled, "stake_units_executada").fillna(0).sum()
    real_units = _safe_numeric(executed_settled, "result_units_real").fillna(0).sum()
    real_roi = (real_units / real_stake * 100) if real_stake else 0.0

    status_series = settled.get("final_settlement_status", pd.Series(index=settled.index, dtype="object")).fillna("pending").astype(str)
    win = int((status_series == "win").sum())
    loss = int((status_series == "loss").sum())
    push = int((status_series == "push").sum())
    half_win = int((status_series == "half_win").sum())
    half_loss = int((status_series == "half_loss").sum())
    decisive = win + loss + half_win + half_loss
    hit_rate = ((win + half_win) / decisive * 100) if decisive else 0.0
    weighted_hit_rate = ((win + (0.5 * half_win) + (0.5 * push)) / len(settled) * 100) if len(settled) else 0.0

    settled_work = settled.copy()
    settled_work["odd_bucket"] = _bucket_odds(_safe_numeric(settled_work, "odd_entrada"))
    settled_work["stake_bucket"] = _bucket_stake(_safe_numeric(settled_work, "stake_units"))

    by_market = _aggregate_performance(settled_work, "market_type")
    by_odd = _aggregate_performance(settled_work, "odd_bucket")
    by_stake = _aggregate_performance(settled_work, "stake_bucket")
    conf_series = settled_work.get("confidence_score", pd.Series(index=settled_work.index)).fillna(-1).astype(str)
    by_conf = _aggregate_performance(settled_work.assign(confidence_bucket=conf_series), "confidence_bucket")

    flag_rows = _split_flags(settled.set_index("bet_id").get("risk_flags"), settled.index) if "bet_id" in settled.columns else pd.DataFrame(columns=["bet_id", "risk_flag"])
    if not flag_rows.empty:
        cols = [c for c in ["bet_id", "stake_units", "result_units_model", "result_units_real", "odd_entrada", "ev_percent"] if c in settled.columns]
        flag_join = flag_rows.merge(settled[cols], on="bet_id", how="left")
        by_flag = _aggregate_performance(flag_join.rename(columns={"risk_flag": "flag"}), "flag")
    else:
        by_flag = []

    if "final_odd_fechamento" in settled.columns:
        clv_df = settled.dropna(subset=["final_odd_fechamento"]).copy()
        clv_df["clv_delta"] = _safe_numeric(clv_df, "odd_entrada") - _safe_numeric(clv_df, "final_odd_fechamento")
        clv_summary = {
            "count": int(len(clv_df)),
            "avg_delta": round(float(clv_df["clv_delta"].mean()), 4) if len(clv_df) else 0.0,
            "positive_rate_percent": round(float((clv_df["clv_delta"] > 0).mean() * 100), 2) if len(clv_df) else 0.0,
        }
    else:
        clv_summary = {"count": 0, "avg_delta": 0.0, "positive_rate_percent": 0.0}

    leagues = sorted(df.get("league", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()) if "league" in df.columns else []
    markets = sorted(df.get("market_type", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()) if "market_type" in df.columns else []
    runs = sorted(df.get("run_id", pd.Series(dtype="object")).dropna().astype(str).unique().tolist(), reverse=True) if "run_id" in df.columns else []
    configs = sorted(df.get("config_name", pd.Series(dtype="object")).dropna().astype(str).unique().tolist()) if "config_name" in df.columns else []

    return {
        "summary": {
            "total_entries": int(total),
            "open_entries": int(len(open_df)),
            "settled_entries": int(len(settled)),
            "executed_entries": int(len(executed)),
            "executed_settled_entries": int(len(executed_settled)),
            "model_units": round(float(model_units), 4),
            "model_stake": round(float(model_stake), 4),
            "model_roi_percent": round(float(model_roi), 2),
            "model_yield_percent": round(float(model_roi), 2),
            "real_units": round(float(real_units), 4),
            "real_stake": round(float(real_stake), 4),
            "real_roi_percent": round(float(real_roi), 2),
            "real_yield_percent": round(float(real_roi), 2),
            "hit_rate_percent": round(float(hit_rate), 2),
            "weighted_hit_rate_percent": round(float(weighted_hit_rate), 2),
            "wins": win,
            "losses": loss,
            "pushes": push,
            "half_wins": half_win,
            "half_losses": half_loss,
        },
        "breakdowns": {
            "by_market": by_market,
            "by_odd_bucket": by_odd,
            "by_stake_bucket": by_stake,
            "by_confidence": by_conf,
            "by_flag": by_flag,
        },
        "clv": clv_summary,
        "entries": _recent_entries(df, limit=entries_limit),
        "filters": {
            "available_leagues": leagues,
            "available_markets": markets,
            "available_runs": runs,
            "available_configs": configs,
        },
    }
