from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from vcbet.paths import DEFAULT_LEDGER_FILE

LEDGER_SCHEMA_VERSION = "phase11_csv_v1"

LEDGER_COLUMNS = [
    "bet_id",
    "ledger_schema_version",
    "ledger_schema_status",
    "ledger_schema_missing_columns",
    "run_id",
    "config_name",
    "config_fingerprint",
    "config_source_path",
    "config_snapshot_file",
    "source_run_id",
    "source_snapshot_ref",
    "odds_source_run_id",
    "xg_source_run_id",
    "odds_snapshot_file",
    "xg_snapshot_file",
    "odds_snapshot_hash",
    "xg_snapshot_hash",
    "odds_snapshot_time",
    "xg_asof",
    "temporal_contract_version",
    "temporal_contract_status",
    "signal_version",
    "pipeline_version",
    "decision_timestamp",
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
    "pricing_signal_type",
    "confidence_score",
    "confidence_score_type",
    "confidence_score_scale",
    "stake_units",
    "entry_reason",
    "risk_flags",
    "pick_safety_status",
    "candidate_stage",
    "safety_gate_reason",
    "decision_policy_status",
    "decision_reject_reason",
    "selection_policy_status",
    "selection_reject_reason",
    "portfolio_risk_status",
    "portfolio_risk_reason",
    "portfolio_exposure_scope",
    "portfolio_exposure_after",
    "market_family",
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

LEDGER_SCHEMA_METADATA_COLUMNS = {
    "ledger_schema_version",
    "ledger_schema_status",
    "ledger_schema_missing_columns",
}

LEDGER_REQUIRED_OPERATIONAL_COLUMNS = {
    "bet_id",
    "run_id",
    "league",
    "match_datetime",
    "home_team",
    "away_team",
    "match_name",
    "market_type",
    "market_scope",
    "side",
    "line",
    "selection_raw",
    "odd_entrada",
    "stake_units",
    "final_bet_status",
    "final_settlement_status",
}


def _empty_value():
    return pd.NA


def normalize_ledger_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Return a ledger-compatible frame while preserving unknown future columns."""
    work = df.copy()
    original_columns = set(work.columns)
    missing_known = [column for column in LEDGER_COLUMNS if column not in work.columns]
    for column in missing_known:
        work[column] = pd.NA

    missing_required = sorted(LEDGER_REQUIRED_OPERATIONAL_COLUMNS - original_columns)
    missing_optional = sorted(
        set(LEDGER_COLUMNS)
        - original_columns
        - LEDGER_REQUIRED_OPERATIONAL_COLUMNS
        - LEDGER_SCHEMA_METADATA_COLUMNS
    )
    if missing_required:
        schema_status = "weak_missing_required"
        missing_columns = "|".join(missing_required)
    elif missing_optional:
        schema_status = "compatible_missing_optional"
        missing_columns = "|".join(missing_optional)
    else:
        schema_status = "complete"
        missing_columns = ""

    work["ledger_schema_version"] = work["ledger_schema_version"].fillna(LEDGER_SCHEMA_VERSION).replace("", LEDGER_SCHEMA_VERSION)
    work["ledger_schema_status"] = work["ledger_schema_status"].fillna(schema_status).replace("", schema_status)
    work["ledger_schema_missing_columns"] = work["ledger_schema_missing_columns"].fillna(missing_columns).replace("", missing_columns)

    for column, default in {
        "bet_executed": "no",
        "auto_bet_status": "open",
        "auto_settlement_status": "pending",
        "final_bet_status": "open",
        "final_settlement_status": "pending",
    }.items():
        work[column] = work[column].fillna(default).replace("", default)

    legacy_result_map = {
        "won": "win",
        "lost": "loss",
        "half_won": "half_win",
        "half_lost": "half_loss",
        "push": "push",
        "voided": "void",
        "cancelled": "void",
    }
    final_bet_status = work["final_bet_status"].astype(str).str.strip().str.lower()
    final_settlement_status = work["final_settlement_status"].astype(str).str.strip().str.lower()
    for old_status, settlement_status in legacy_result_map.items():
        mask = final_bet_status.eq(old_status) & final_settlement_status.isin({"", "nan", "none", "<na>", "pending"})
        work.loc[mask, "final_settlement_status"] = settlement_status
    resolved_settlement = work["final_settlement_status"].astype(str).str.strip().str.lower()
    settled_mask = resolved_settlement.isin({"win", "loss", "half_win", "half_loss", "push", "void"})
    open_like = work["final_bet_status"].astype(str).str.strip().str.lower().isin({"", "nan", "none", "<na>", "open", "pending", "won", "lost", "half_won", "half_lost", "push"})
    work.loc[settled_mask & open_like, "final_bet_status"] = "settled"

    ordered = [column for column in LEDGER_COLUMNS if column in work.columns]
    extra = [column for column in work.columns if column not in LEDGER_COLUMNS]
    return work[ordered + extra].copy()



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

def ensure_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    path = Path(ledger_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pd.DataFrame(columns=LEDGER_COLUMNS).to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def load_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> pd.DataFrame:
    path = ensure_ledger(ledger_file)
    df = pd.read_csv(path, sep=";")
    return normalize_ledger_schema(df)


def save_ledger(df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> Path:
    path = ensure_ledger(ledger_file)
    normalize_ledger_schema(df).to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def _pick_value(pick: pd.Series, *names: str, default=pd.NA):
    for name in names:
        value = pick.get(name)
        if pd.notna(value) and str(value).strip() != "":
            return value
    return default


def _pick_to_ledger_row(pick: pd.Series) -> dict:
    decision_timestamp = _pick_value(pick, "decision_timestamp", "generated_at")
    return {
        "bet_id": pick["bet_id"],
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_schema_status": "complete",
        "ledger_schema_missing_columns": "",
        "run_id": pick["run_id"],
        "config_name": _pick_value(pick, "config_name", "strategy_config_name"),
        "config_fingerprint": _pick_value(pick, "config_fingerprint", "strategy_config_fingerprint"),
        "config_source_path": _pick_value(pick, "config_source_path", "strategy_config_source_path"),
        "config_snapshot_file": _pick_value(pick, "config_snapshot_file", "strategy_config_file"),
        "source_run_id": _pick_value(pick, "source_run_id"),
        "source_snapshot_ref": _pick_value(pick, "source_snapshot_ref"),
        "odds_source_run_id": _pick_value(pick, "odds_source_run_id"),
        "xg_source_run_id": _pick_value(pick, "xg_source_run_id"),
        "odds_snapshot_file": _pick_value(pick, "odds_snapshot_file"),
        "xg_snapshot_file": _pick_value(pick, "xg_snapshot_file"),
        "odds_snapshot_hash": _pick_value(pick, "odds_snapshot_hash"),
        "xg_snapshot_hash": _pick_value(pick, "xg_snapshot_hash"),
        "odds_snapshot_time": _pick_value(pick, "odds_snapshot_time"),
        "xg_asof": _pick_value(pick, "xg_asof"),
        "temporal_contract_version": _pick_value(pick, "temporal_contract_version"),
        "temporal_contract_status": _pick_value(pick, "temporal_contract_status"),
        "signal_version": _pick_value(pick, "signal_version"),
        "pipeline_version": _pick_value(pick, "pipeline_version"),
        "decision_timestamp": decision_timestamp,
        "created_at": decision_timestamp,
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
        "pricing_signal_type": pick.get("pricing_signal_type"),
        "confidence_score": pick.get("confidence_score"),
        "confidence_score_type": pick.get("confidence_score_type"),
        "confidence_score_scale": pick.get("confidence_score_scale"),
        "stake_units": pick.get("stake_units"),
        "entry_reason": pick.get("entry_reason"),
        "risk_flags": pick.get("risk_flags"),
        "pick_safety_status": pick.get("pick_safety_status", "safe"),
        "candidate_stage": pick.get("candidate_stage", "official_accepted_pick"),
        "safety_gate_reason": pick.get("safety_gate_reason", ""),
        "decision_policy_status": pick.get("decision_policy_status"),
        "decision_reject_reason": pick.get("decision_reject_reason"),
        "selection_policy_status": pick.get("selection_policy_status"),
        "selection_reject_reason": pick.get("selection_reject_reason"),
        "portfolio_risk_status": pick.get("portfolio_risk_status"),
        "portfolio_risk_reason": pick.get("portfolio_risk_reason"),
        "portfolio_exposure_scope": pick.get("portfolio_exposure_scope"),
        "portfolio_exposure_after": pick.get("portfolio_exposure_after"),
        "market_family": pick.get("market_family"),
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

    ledger_df, _ = deduplicate_ledger_rows(ledger_df)
    existing_ids = set(ledger_df["bet_id"].dropna().astype(str).tolist())
    existing_keys = {bet_identity_key(row) for _, row in ledger_df.iterrows()}
    new_rows = []
    for _, row in picks_df.iterrows():
        bet_id = str(row["bet_id"])
        identity_key = bet_identity_key(row)
        if bet_id in existing_ids or identity_key in existing_keys:
            continue
        new_rows.append(_pick_to_ledger_row(row))
        existing_ids.add(bet_id)
        existing_keys.add(identity_key)

    if new_rows:
        if ledger_df.empty:
            ledger_df = normalize_ledger_schema(pd.DataFrame(new_rows))
        else:
            for new_row in new_rows:
                ledger_df.loc[len(ledger_df)] = {column: new_row.get(column, pd.NA) for column in ledger_df.columns}

    ledger_df, _removed_duplicates = deduplicate_ledger_rows(ledger_df)
    save_ledger(ledger_df, path)
    return path, len(new_rows), len(ledger_df)
