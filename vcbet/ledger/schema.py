from __future__ import annotations

import re

import pandas as pd


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
    "ledger_portfolio_gate_status",
    "ledger_portfolio_gate_reason",
    "ledger_portfolio_related_bet_id",
    "ledger_portfolio_gate_details",
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
    "closing_odd",
    "closing_bookmaker",
    "closing_snapshot_time",
    "closing_source",
    "closing_update_status",
    "closing_update_error",
    "settlement_source",
    "settlement_confidence",
    "settlement_note",
    "sofascore_event_id",
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


def normalize_sofascore_event_id(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    if re.fullmatch(r"\d+", text):
        return text
    match = re.search(r"(?:source_event_id|sofascore_event_id)=([0-9]+(?:\.0+)?)", text)
    if match:
        return normalize_sofascore_event_id(match.group(1))
    return text


def extract_sofascore_event_id_from_note(value) -> str:
    if pd.isna(value):
        return ""
    match = re.search(r"(?:source_event_id|sofascore_event_id)=([0-9]+(?:\.0+)?)", str(value))
    if not match:
        return ""
    return normalize_sofascore_event_id(match.group(1))


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

    work["sofascore_event_id"] = work["sofascore_event_id"].apply(normalize_sofascore_event_id)
    derived_event_ids = work["settlement_note"].apply(extract_sofascore_event_id_from_note)
    missing_event_id = work["sofascore_event_id"].astype(str).str.strip() == ""
    work.loc[missing_event_id & (derived_event_ids.astype(str).str.strip() != ""), "sofascore_event_id"] = derived_event_ids
    work["sofascore_event_id"] = work["sofascore_event_id"].replace("", pd.NA)

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

