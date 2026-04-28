from __future__ import annotations

from pathlib import Path

import pandas as pd

from vcbet.core.ledger_portfolio_gate import check_against_open_ledger, is_official_ledger_path
from vcbet.domain.contracts import LedgerAppendResult
from vcbet.ledger.identity import bet_identity_key, deduplicate_ledger_rows
from vcbet.ledger.repository import (
    ensure_ledger_unlocked,
    ledger_file_lock,
    load_ledger_unlocked,
    save_ledger_unlocked,
    write_ledger_csv_unlocked,
)
from vcbet.ledger.schema import LEDGER_SCHEMA_VERSION, normalize_ledger_schema
from vcbet.paths import DEFAULT_LEDGER_FILE


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
        "ledger_portfolio_gate_status": pick.get("ledger_portfolio_gate_status", "passed"),
        "ledger_portfolio_gate_reason": pick.get("ledger_portfolio_gate_reason", ""),
        "ledger_portfolio_related_bet_id": pick.get("ledger_portfolio_related_bet_id", ""),
        "ledger_portfolio_gate_details": pick.get("ledger_portfolio_gate_details", ""),
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
        "closing_odd": pd.NA,
        "closing_bookmaker": pd.NA,
        "closing_snapshot_time": pd.NA,
        "closing_source": pd.NA,
        "closing_update_status": pd.NA,
        "closing_update_error": pd.NA,
        "settlement_source": pd.NA,
        "settlement_confidence": pd.NA,
        "settlement_note": pd.NA,
        "sofascore_event_id": _pick_value(pick, "sofascore_event_id", "source_event_id"),
        "override_reason": pd.NA,
        "override_updated_at": pd.NA,
        "result_units_model": pd.NA,
        "result_units_real": pd.NA,
    }


def _blocked_file_for_ledger(ledger_file: Path) -> Path:
    return ledger_file.parent / "ledger_portfolio_blocked.csv"


def _persist_blocked_candidates(blocked_rows: list[dict], ledger_file: Path) -> None:
    if not blocked_rows:
        return
    path = _blocked_file_for_ledger(ledger_file)
    new_df = pd.DataFrame(blocked_rows)
    if path.exists():
        existing = pd.read_csv(path, sep=";")
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = new_df
    write_ledger_csv_unlocked(combined, path)


def append_new_picks_to_ledger_result(picks_df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> tuple[Path, LedgerAppendResult]:
    with ledger_file_lock(ledger_file):
        path = ensure_ledger_unlocked(ledger_file)
        ledger_df = load_ledger_unlocked(path)
        attempted = int(len(picks_df))
        if picks_df.empty:
            save_ledger_unlocked(ledger_df, path)
            return path, LedgerAppendResult(
                appended=0,
                blocked=0,
                duplicate=0,
                provenance={"ledger_file": str(path), "total_rows": int(len(ledger_df)), "attempted": attempted},
            )

        ledger_df, _ = deduplicate_ledger_rows(ledger_df)
        existing_ids = set(ledger_df["bet_id"].dropna().astype(str).tolist())
        existing_keys = {bet_identity_key(row) for _, row in ledger_df.iterrows()}
        existing_key_to_bet_id = {bet_identity_key(row): str(row.get("bet_id") or "") for _, row in ledger_df.iterrows()}
        new_rows = []
        blocked_rows = []
        duplicate_count = 0
        blocked_count = 0
        reasons: set[str] = set()
        apply_ledger_gate = is_official_ledger_path(path)
        for _, row in picks_df.iterrows():
            bet_id = str(row["bet_id"])
            identity_key = bet_identity_key(row)
            if bet_id in existing_ids or identity_key in existing_keys:
                duplicate_count += 1
                blocked_count += 1
                reasons.add("LEDGER_DUPLICATE_OPEN_PICK")
                if apply_ledger_gate:
                    blocked = row.to_dict()
                    blocked.update(
                        {
                            "candidate_stage": "ledger_portfolio_blocked_candidate",
                            "portfolio_risk_status": "rejected",
                            "portfolio_risk_reason": "LEDGER_DUPLICATE_OPEN_PICK",
                            "ledger_portfolio_gate_status": "blocked",
                            "ledger_portfolio_gate_reason": "LEDGER_DUPLICATE_OPEN_PICK",
                            "ledger_portfolio_related_bet_id": bet_id if bet_id in existing_ids else existing_key_to_bet_id.get(identity_key, ""),
                            "ledger_portfolio_gate_details": "duplicate bet_id or stable identity already present in official ledger",
                        }
                    )
                    blocked_rows.append(blocked)
                continue
            if apply_ledger_gate:
                gate = check_against_open_ledger(row.to_dict(), ledger_df)
                if gate["status"] == "blocked":
                    blocked_count += 1
                    reasons.add(str(gate["reason"]))
                    blocked = row.to_dict()
                    blocked.update(
                        {
                            "candidate_stage": "ledger_portfolio_blocked_candidate",
                            "portfolio_risk_status": "rejected",
                            "portfolio_risk_reason": gate["reason"],
                            "selection_policy_status": "rejected_by_ledger_portfolio_gate",
                            "selection_reject_reason": gate["reason"],
                            "ledger_portfolio_gate_status": gate["status"],
                            "ledger_portfolio_gate_reason": gate["reason"],
                            "ledger_portfolio_related_bet_id": gate["related_bet_id"],
                            "ledger_portfolio_gate_details": gate["details"],
                        }
                    )
                    blocked_rows.append(blocked)
                    continue
                row = row.copy()
                row["ledger_portfolio_gate_status"] = "passed"
                row["ledger_portfolio_gate_reason"] = ""
                row["ledger_portfolio_related_bet_id"] = ""
                row["ledger_portfolio_gate_details"] = ""
            new_rows.append(_pick_to_ledger_row(row))
            existing_ids.add(bet_id)
            existing_keys.add(identity_key)
            existing_key_to_bet_id[identity_key] = bet_id

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            if ledger_df.empty:
                ledger_df = normalize_ledger_schema(new_df)
            else:
                for column in ledger_df.columns:
                    if column not in new_df.columns:
                        new_df[column] = pd.NA
                new_df = new_df[ledger_df.columns]
                ledger_df = pd.concat([ledger_df, new_df], ignore_index=True)

        ledger_df, _removed_duplicates = deduplicate_ledger_rows(ledger_df)
        save_ledger_unlocked(ledger_df, path)
        if apply_ledger_gate:
            _persist_blocked_candidates(blocked_rows, path)
        return path, LedgerAppendResult(
            appended=len(new_rows),
            blocked=blocked_count,
            duplicate=duplicate_count,
            provenance={
                "ledger_file": str(path),
                "total_rows": int(len(ledger_df)),
                "attempted": attempted,
                "official_gate": apply_ledger_gate,
            },
            reasons=tuple(sorted(reasons)),
        )


def append_new_picks_to_ledger(picks_df: pd.DataFrame, ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> tuple[Path, int, int]:
    path, result = append_new_picks_to_ledger_result(picks_df, ledger_file)
    return path, result.appended, int(result.provenance["total_rows"])
