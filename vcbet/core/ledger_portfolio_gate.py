from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from vcbet.core.line_selector import market_family
from vcbet.paths import DEFAULT_LEDGER_FILE


OFFICIAL_LEDGER_REASONS = {
    "duplicate": "LEDGER_DUPLICATE_OPEN_PICK",
    "correlated": "LEDGER_CORRELATED_OPEN_PICK",
    "contradictory": "LEDGER_CONTRADICTORY_OPEN_PICK",
}


def is_official_ledger_path(ledger_file: str | Path) -> bool:
    try:
        return Path(ledger_file).resolve() == DEFAULT_LEDGER_FILE.resolve()
    except Exception:
        return False


def _clean(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().casefold().split())


def _line_float(value: Any) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_event(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    cand_url = _clean(candidate.get("event_url"))
    existing_url = _clean(existing.get("event_url"))
    if cand_url and existing_url and cand_url == existing_url:
        return True
    return (
        _clean(candidate.get("league")) == _clean(existing.get("league"))
        and _clean(candidate.get("match_datetime"))[:16] == _clean(existing.get("match_datetime"))[:16]
        and _clean(candidate.get("home_team")) == _clean(existing.get("home_team"))
        and _clean(candidate.get("away_team")) == _clean(existing.get("away_team"))
    )


def _same_target(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    return (
        _clean(candidate.get("target_team_role") or "geral") == _clean(existing.get("target_team_role") or "geral")
        and _clean(candidate.get("target_team_name") or "geral") == _clean(existing.get("target_team_name") or "geral")
    )


def _same_or_near_line(candidate: dict[str, Any], existing: dict[str, Any], tolerance: float = 0.25) -> bool:
    cand_line = _line_float(candidate.get("line"))
    existing_line = _line_float(existing.get("line"))
    if cand_line is None or existing_line is None:
        return _clean(candidate.get("selection_raw")) == _clean(existing.get("selection_raw"))
    return abs(cand_line - existing_line) <= tolerance


def _is_open_entry(row: dict[str, Any]) -> bool:
    bet_status = _clean(row.get("final_bet_status"))
    settlement_status = _clean(row.get("final_settlement_status"))
    if bet_status in {"settled", "voided", "cancelled", "postponed", "unmatched"}:
        return False
    if settlement_status in {"win", "loss", "half_win", "half_loss", "push", "void"}:
        return False
    return True


def _is_contradictory(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    family = market_family(candidate)
    if family != market_family(existing):
        return False
    cand_side = _clean(candidate.get("side"))
    existing_side = _clean(existing.get("side"))
    if family in {"goals_total", "team_goals"}:
        if {cand_side, existing_side} != {"over", "under"}:
            return False
        if family == "team_goals" and not _same_target(candidate, existing):
            return False
        return _same_or_near_line(candidate, existing)
    if family == "btts":
        return {cand_side, existing_side} == {"yes", "no"}
    if family == "handicap":
        return cand_side and existing_side and cand_side != existing_side
    return False


def check_against_open_ledger(candidate: dict[str, Any], ledger_rows: pd.DataFrame) -> dict[str, Any]:
    """Return ledger-level portfolio gate status for one candidate.

    This gate is intentionally conservative and only compares against already
    open/unsettled official-ledger entries. Run-level pricing and selection
    remain unchanged upstream.
    """
    if ledger_rows.empty:
        return {"status": "passed", "reason": "", "related_bet_id": "", "details": ""}

    candidate_family = market_family(candidate)
    for _, existing_row in ledger_rows.iterrows():
        existing = existing_row.to_dict()
        if not _is_open_entry(existing) or not _same_event(candidate, existing):
            continue

        related = str(existing.get("bet_id") or "")
        existing_family = market_family(existing)
        same_family = candidate_family == existing_family
        same_side = _clean(candidate.get("side")) == _clean(existing.get("side"))

        if same_family and same_side and _same_target(candidate, existing) and _same_or_near_line(candidate, existing):
            return {
                "status": "blocked",
                "reason": OFFICIAL_LEDGER_REASONS["duplicate"],
                "related_bet_id": related,
                "details": f"family={candidate_family}|existing_line={existing.get('line')}|existing_run={existing.get('run_id')}|existing_config={existing.get('config_name')}",
            }

        if _is_contradictory(candidate, existing):
            return {
                "status": "blocked",
                "reason": OFFICIAL_LEDGER_REASONS["contradictory"],
                "related_bet_id": related,
                "details": f"family={candidate_family}|existing_side={existing.get('side')}|existing_line={existing.get('line')}|existing_run={existing.get('run_id')}|existing_config={existing.get('config_name')}",
            }

        if candidate_family in {"goals_total", "team_goals", "btts"} and existing_family in {"goals_total", "team_goals", "btts"}:
            return {
                "status": "blocked",
                "reason": OFFICIAL_LEDGER_REASONS["correlated"],
                "related_bet_id": related,
                "details": f"candidate_family={candidate_family}|existing_family={existing_family}|existing_run={existing.get('run_id')}|existing_config={existing.get('config_name')}",
            }

    return {"status": "passed", "reason": "", "related_bet_id": "", "details": ""}
