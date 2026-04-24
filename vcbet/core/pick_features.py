from __future__ import annotations

import pandas as pd

from vcbet.core.pick_filter import is_xg_fallback
from vcbet.core.pricing_engine import expected_value_decimal, fair_odd_from_probs


def _display_selection(row: pd.Series) -> str:
    """Seleção legível e identificável para relatórios, comparison e ledger."""
    selection = str(row.get("selection_raw", "")).strip()
    if str(row.get("market_type", "")).strip() == "team_total":
        team = str(row.get("target_team_name", "")).strip()
        if team and team.lower() not in {"nan", "none", "<na>", "geral"}:
            return f"{team} {selection}".strip()
    return selection

def build_candidate_row(
    *,
    run_id: str,
    odds_run_id: str,
    xg_run_id: str,
    generated_at: str,
    row: pd.Series,
    home_match_status: str,
    away_match_status: str,
    lambda_bundle: dict[str, float],
    pricing_result: dict,
    home_xg_row: pd.Series,
    away_xg_row: pd.Series,
) -> dict:
    probs = pricing_result["probs"]
    fair_odd = fair_odd_from_probs(probs)
    ev_decimal = expected_value_decimal(probs, float(row["odd"]))

    return {
        "run_id": run_id,
        "odds_source_run_id": odds_run_id,
        "xg_source_run_id": xg_run_id,
        "generated_at": generated_at,
        "league": row["league"],
        "match_datetime": row["match_datetime"],
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "match_name": row["match_name"],
        "market_type": row["market_type"],
        "market_scope": row["market_scope"],
        "market_raw": row["market_raw"],
        "selection_raw": _display_selection(row),
        "line": None if pd.isna(row.get("line")) else float(row.get("line")),
        "side": row.get("side"),
        "target_team_role": row.get("target_team_role"),
        "target_team_name": row.get("target_team_name"),
        "event_url": row.get("event_url"),
        "odd_entrada": float(row["odd"]),
        "prob_model": round(probs["win"] + 0.5 * probs["half_win"], 6),
        "odd_justa": fair_odd,
        "ev_decimal": ev_decimal,
        "mu_total": lambda_bundle["mu_total"],
        "lambda_home": lambda_bundle["lambda_home"],
        "lambda_away": lambda_bundle["lambda_away"],
        "match_status_home": home_match_status,
        "match_status_away": away_match_status,
        "xg_fallback_home": is_xg_fallback(home_xg_row),
        "xg_fallback_away": is_xg_fallback(away_xg_row),
    }
