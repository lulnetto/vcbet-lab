from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from vcbet.core.decision_policy import build_bet_id, evaluate_pick_candidate_with_details
from vcbet.core.market_exceptions import EV_EXCEPTION_BTTS_YES_EXPERIMENTAL
from vcbet.core.run_utils import build_manifest, save_manifest
from vcbet.core.selection import market_family as infer_market_family
from vcbet.core.sport_sense_policy import (
    _apply_team_total_semantics,
    _team_total_policy,
    infer_team_role,
    normalize_btts_side,
)


AUDIT_STATUS_VALUES = {
    "kept",
    "blocked",
    "penalized",
    "selected",
    "discarded",
    "not_applicable",
    "unknown",
}

AUDIT_COLS = [
    "run_group_id",
    "run_id",
    "config_name",
    "ledger_path",
    "source_snapshot_id",
    "match_datetime",
    "league",
    "home_team",
    "away_team",
    "market_type",
    "market_family",
    "selection",
    "selection_normalized",
    "line",
    "odd_entrada",
    "odd",
    "ev_percent",
    "confidence_score",
    "entry_quality_score",
    "original_stake",
    "stake",
    "market_filter_status",
    "market_filter_reason",
    "odd_policy_status",
    "odd_policy_reason",
    "ev_policy_status",
    "ev_policy_reason",
    "market_exception_applied",
    "market_exception_reason",
    "side_rule_status",
    "side_rule_reason",
    "side_rule_evaluation",
    "sport_sense_status",
    "sport_sense_reason",
    "sport_sense_evaluation",
    "team_role",
    "team_role_source",
    "stake_policy_applied",
    "stake_policy_reason",
    "portfolio_status",
    "portfolio_reason",
    "final_selected",
    "final_reject_reason",
]

SUMMARY_GROUP_COLS = [
    "config_name",
    "market_type",
    "final_selected",
    "final_reject_reason",
    "sport_sense_reason",
    "odd_policy_reason",
    "ev_policy_reason",
    "portfolio_reason",
]

MARKET_FILTER_REASONS = {
    "unsupported_market",
    "market_disabled_by_config",
    "league_disabled_by_config",
}
ODD_POLICY_REASONS = {
    "odd_in_blocked_range",
    "odd_outside_allowed_ranges",
    "odd_out_of_range",
    "ODD_IN_BLOCKED_RANGE",
    "ODD_OUTSIDE_ALLOWED_RANGES",
    "ODD_OUT_OF_RANGE",
}
EV_POLICY_REASONS = {
    "ev_below_market_min",
    "edge_below_min",
    "ev_outlier_above_max",
    "EV_BELOW_MARKET_MIN",
    "EDGE_BELOW_MIN",
    "EV_OUTLIER_ABOVE_MAX",
}
SIDE_RULE_REASONS = {"BTTS_SIDE_BLOCKED"}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "nan", "none", "<na>", "null"}


def _text(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    return str(value).strip()


def _clean_key(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _num(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    text = _clean_key(value)
    if text in {"1", "true", "yes", "sim", "y"}:
        return True
    if text in {"0", "false", "no", "nao", "não", "n"}:
        return False
    return None


def _first(payload: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        value = payload.get(name)
        if not _is_missing(value):
            return value
    return default


def _normalize_reason(value: Any, default: str = "UNKNOWN") -> str:
    text = _text(value)
    if not text:
        return default
    return text.strip().upper()


def _normalize_sport_sense_status(value: Any) -> str:
    text = _clean_key(value)
    if text in {"approved", "eligible", "safe", "accepted", "passed", "kept"}:
        return "kept"
    if text in AUDIT_STATUS_VALUES:
        return text
    return "unknown"


def _candidate_bet_id(candidate: dict[str, Any]) -> str:
    existing = _text(candidate.get("bet_id"))
    if existing:
        return existing
    try:
        return build_bet_id(
            _text(candidate.get("match_datetime")),
            _text(candidate.get("league")),
            _text(candidate.get("home_team")),
            _text(candidate.get("away_team")),
            _text(candidate.get("market_type")),
            _text(candidate.get("market_scope"), "full_time"),
            None if _is_missing(candidate.get("side")) else _text(candidate.get("side")),
            _num(candidate.get("line")),
            None if _is_missing(candidate.get("target_team_role")) else _text(candidate.get("target_team_role")),
            None if _is_missing(candidate.get("target_team_name")) else _text(candidate.get("target_team_name")),
            _text(_first(candidate, "selection_raw", "selection", "selection_name")),
        )
    except Exception:
        raw = "|".join(
            _text(candidate.get(name))
            for name in (
                "match_datetime",
                "league",
                "home_team",
                "away_team",
                "market_type",
                "side",
                "line",
                "target_team_role",
                "target_team_name",
                "selection_raw",
            )
        )
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    return [dict(row) for row in df.to_dict("records")]


def _num_key(value: Any) -> str:
    number = _num(value)
    if number is None:
        return ""
    return f"{number:.6f}".rstrip("0").rstrip(".")


def _candidate_match_key(candidate: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _candidate_bet_id(candidate),
        _clean_key(candidate.get("event_url")),
        _num_key(_first(candidate, "line", default="")),
        _num_key(_first(candidate, "odd_entrada", "odd", default="")),
        _clean_key(_first(candidate, "selection_raw", "selection", "selection_name", default="")),
    )


def _stage_index(df: pd.DataFrame | None) -> dict[str, Any]:
    by_match: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    by_bet_id: dict[str, list[dict[str, Any]]] = {}
    for occurrence_id, row in enumerate(_records(df)):
        bet_id = _candidate_bet_id(row)
        row["bet_id"] = bet_id
        row["__audit_occurrence_id"] = occurrence_id
        by_match.setdefault(_candidate_match_key(row), []).append(row)
        by_bet_id.setdefault(bet_id, []).append(row)
    return {"by_match": by_match, "by_bet_id": by_bet_id, "consumed": set()}


def _pop_bucket(bucket: list[dict[str, Any]] | None, consumed: set[int]) -> dict[str, Any] | None:
    if not bucket:
        return None
    while bucket:
        row = bucket.pop(0)
        occurrence_id = row.get("__audit_occurrence_id")
        if occurrence_id in consumed:
            continue
        consumed.add(occurrence_id)
        return row
    return None


def _pop_stage(index: dict[str, Any], raw: dict[str, Any], *, allow_bet_id_fallback: bool = True) -> dict[str, Any] | None:
    consumed = index["consumed"]
    row = _pop_bucket(index["by_match"].get(_candidate_match_key(raw)), consumed)
    if row is not None or not allow_bet_id_fallback:
        return row
    return _pop_bucket(index["by_bet_id"].get(_candidate_bet_id(raw)), consumed)


def _evaluate_raw_candidate_records(df_raw_candidates: pd.DataFrame) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    evaluated_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for raw in _records(df_raw_candidates):
        bet_id = _candidate_bet_id(raw)
        raw["bet_id"] = bet_id
        try:
            accepted, reject_reason, rejected_payload = evaluate_pick_candidate_with_details(raw)
        except Exception as exc:
            evaluated_rows.append(
                (
                    raw,
                    {
                        "accepted": False,
                        "reject_reason": "audit_evaluation_failed",
                        "payload": {**raw, "audit_evaluation_error": str(exc)},
                    },
                )
            )
            continue
        payload = accepted or rejected_payload or raw
        payload = dict(payload)
        payload["bet_id"] = _candidate_bet_id(payload)
        evaluated_rows.append(
            (
                raw,
                {
                    "accepted": accepted is not None,
                    "reject_reason": reject_reason,
                    "payload": payload,
                },
            )
        )
    return evaluated_rows


def _selection_normalized(payload: dict[str, Any]) -> str:
    market_type = _clean_key(payload.get("market_type")) or "unknown"
    side = _clean_key(payload.get("side"))
    if market_type == "btts":
        side = normalize_btts_side(
            _first(payload, "side", "selection", "selection_name", "selection_raw")
        )
    target_role = _clean_key(_first(payload, "target_team_role", "team_role", default="geral")) or "geral"
    target_name = _clean_key(_first(payload, "target_team_name", default="geral")) or "geral"
    line = _first(payload, "line", default="")
    line_part = "" if _is_missing(line) else str(line)
    return "|".join(
        part
        for part in (market_type, target_role, target_name, side or "unknown", line_part)
        if part != ""
    )


def _has_btts_side_rule(runtime_config: Any) -> bool:
    rules = getattr(runtime_config, "side_rules", None)
    if not isinstance(rules, dict):
        payload = getattr(runtime_config, "payload", {})
        rules = payload.get("side_rules") if isinstance(payload, dict) else {}
    btts = rules.get("btts") if isinstance(rules, dict) else None
    return isinstance(btts, dict) and bool(btts)


def _btts_side_rules(runtime_config: Any) -> dict[str, Any]:
    rules = getattr(runtime_config, "side_rules", None)
    if not isinstance(rules, dict):
        payload = getattr(runtime_config, "payload", {})
        rules = payload.get("side_rules") if isinstance(payload, dict) else {}
    btts = rules.get("btts") if isinstance(rules, dict) else None
    return dict(btts) if isinstance(btts, dict) else {}


def _evaluation(status: str, reason: str) -> str:
    normalized_status = status if status in AUDIT_STATUS_VALUES else "unknown"
    normalized_reason = _normalize_reason(reason)
    return f"{normalized_status}:{normalized_reason}"


def _side_rule_diagnostic(payload: dict[str, Any], runtime_config: Any) -> str:
    if _clean_key(payload.get("market_type")) != "btts":
        return _evaluation("not_applicable", "NOT_APPLICABLE")
    rules = _btts_side_rules(runtime_config)
    if not rules:
        return _evaluation("not_applicable", "NOT_APPLICABLE")

    side = normalize_btts_side(_first(payload, "side", "selection", "selection_name", "selection_raw"))
    if side == "unknown":
        return _evaluation("unknown", "BTTS_SIDE_UNKNOWN")

    blocked = {
        normalize_btts_side(item)
        for item in rules.get("blocked_sides", [])
        if not _is_missing(item)
    } if isinstance(rules.get("blocked_sides"), list) else set()
    if side in blocked:
        return _evaluation("blocked", "BTTS_SIDE_BLOCKED")

    if "allowed_sides" in rules:
        allowed = {
            normalize_btts_side(item)
            for item in rules.get("allowed_sides", [])
            if not _is_missing(item)
        } if isinstance(rules.get("allowed_sides"), list) else set()
        if side not in allowed:
            return _evaluation("blocked", "BTTS_SIDE_BLOCKED")

    return _evaluation("kept", "KEPT")


def _sport_sense_diagnostic(payload: dict[str, Any], runtime_config: Any) -> str:
    if _clean_key(payload.get("market_type")) != "team_total":
        return _evaluation("not_applicable", "NOT_APPLICABLE")
    try:
        if not _team_total_policy(runtime_config):
            return _evaluation("not_applicable", "NOT_APPLICABLE")
        diagnostic = dict(payload)
        role, source = infer_team_role(diagnostic)
        diagnostic["team_role"] = role
        diagnostic["team_role_source"] = source
        status, reason = _apply_team_total_semantics(diagnostic, runtime_config)
        return _evaluation(_normalize_sport_sense_status(status), reason)
    except Exception as exc:
        return _evaluation("unknown", f"EVALUATION_ERROR_{type(exc).__name__}")


def _stake_policy_status(payload: dict[str, Any], reached_profile_policy: bool) -> tuple[str, str]:
    if not reached_profile_policy:
        return "not_applicable", "NOT_APPLICABLE"
    sport_status = _normalize_sport_sense_status(payload.get("sport_sense_status"))
    if sport_status == "blocked":
        return "not_applicable", "PRE_STAKE_POLICY_BLOCKED"

    applied = _boolish(payload.get("stake_policy_applied"))
    original = _num(_first(payload, "original_stake", "stake_units", "stake", default=None))
    stake = _num(_first(payload, "stake", "stake_units", default=None))
    reason = _text(payload.get("stake_policy_reason")) or "KEPT"
    if original is not None and stake is not None and stake < original:
        return "penalized", reason
    if applied is True or sport_status in {"kept", "penalized"}:
        return "kept", reason
    if applied is False:
        return "not_applicable", reason if reason else "NOT_APPLICABLE"
    return "unknown", "UNKNOWN"


def _audit_row(
    *,
    raw: dict[str, Any],
    eval_meta: dict[str, Any],
    payload: dict[str, Any],
    runtime_config: Any,
    run_id: str,
    run_group_id: str | None,
    ledger_path: str | None,
    source_snapshot_id: str | None,
    approved_candidate: dict[str, Any] | None,
    profile_blocked: dict[str, Any] | None,
    portfolio_rejected: dict[str, Any] | None,
    final_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    old_reject = eval_meta.get("reject_reason")
    old_reject_reason = _normalize_reason(old_reject, default="")
    reached_old_filter = old_reject is None or bool(eval_meta.get("accepted"))
    reached_profile_policy = any(
        item is not None
        for item in (approved_candidate, profile_blocked, portfolio_rejected, final_candidate)
    )
    final_selected = final_candidate is not None

    if old_reject in MARKET_FILTER_REASONS:
        market_filter_status = "blocked"
        market_filter_reason = old_reject_reason
    else:
        market_filter_status = "kept"
        market_filter_reason = "KEPT"

    sport_reason = _normalize_reason(payload.get("sport_sense_reason"), default="")
    market_exception_reason = _normalize_reason(payload.get("market_exception_reason"), default="")
    market_exception_applied = _boolish(payload.get("market_exception_applied")) is True or market_exception_reason == EV_EXCEPTION_BTTS_YES_EXPERIMENTAL
    if old_reject in ODD_POLICY_REASONS or sport_reason in ODD_POLICY_REASONS:
        odd_policy_status = "blocked"
        odd_policy_reason = sport_reason if sport_reason in ODD_POLICY_REASONS else old_reject_reason
    elif market_filter_status == "blocked":
        odd_policy_status = "not_applicable"
        odd_policy_reason = "NOT_APPLICABLE"
    else:
        odd_policy_status = "kept"
        odd_policy_reason = "KEPT"

    if old_reject in EV_POLICY_REASONS or sport_reason in EV_POLICY_REASONS:
        ev_policy_status = "blocked"
        ev_policy_reason = sport_reason if sport_reason in EV_POLICY_REASONS else old_reject_reason
    elif market_exception_applied:
        ev_policy_status = "kept"
        ev_policy_reason = market_exception_reason or EV_EXCEPTION_BTTS_YES_EXPERIMENTAL
    elif market_filter_status == "blocked" or odd_policy_status == "blocked":
        ev_policy_status = "not_applicable"
        ev_policy_reason = "NOT_APPLICABLE"
    else:
        ev_policy_status = "kept"
        ev_policy_reason = "KEPT"

    market_type = _clean_key(payload.get("market_type"))
    if not reached_profile_policy:
        side_rule_status = "not_applicable"
        side_rule_reason = "NOT_APPLICABLE"
        sport_sense_status = "not_applicable"
        sport_sense_reason = "NOT_APPLICABLE"
    else:
        if market_type == "btts" and _has_btts_side_rule(runtime_config):
            if sport_reason in SIDE_RULE_REASONS:
                side_rule_status = "blocked"
                side_rule_reason = sport_reason
            else:
                side_rule_status = "kept"
                side_rule_reason = "KEPT"
        else:
            side_rule_status = "not_applicable"
            side_rule_reason = "NOT_APPLICABLE"
        sport_sense_status = _normalize_sport_sense_status(payload.get("sport_sense_status"))
        sport_sense_reason = sport_reason or ("UNKNOWN" if sport_sense_status == "unknown" else "KEPT")

    stake_policy_status, stake_policy_reason = _stake_policy_status(payload, reached_profile_policy)
    side_rule_evaluation = _side_rule_diagnostic(payload, runtime_config)
    sport_sense_evaluation = _sport_sense_diagnostic(payload, runtime_config)

    if final_selected:
        portfolio_status = "selected"
        portfolio_reason = "SELECTED"
        final_reject_reason = "SELECTED"
    elif portfolio_rejected is not None:
        portfolio_status = "discarded"
        portfolio_reason = _normalize_reason(
            _first(portfolio_rejected, "portfolio_reject_reason", "selection_reject_reason"),
            default="PORTFOLIO_DISCARDED",
        )
        final_reject_reason = portfolio_reason
    elif profile_blocked is not None:
        portfolio_status = "not_applicable"
        portfolio_reason = "PRE_PORTFOLIO_BLOCKED"
        final_reject_reason = sport_sense_reason
    elif old_reject:
        portfolio_status = "not_applicable"
        portfolio_reason = "PRE_PORTFOLIO_BLOCKED"
        final_reject_reason = old_reject_reason or "UNKNOWN"
    elif reached_old_filter:
        portfolio_status = "unknown"
        portfolio_reason = "UNKNOWN"
        final_reject_reason = "UNKNOWN"
    else:
        portfolio_status = "unknown"
        portfolio_reason = "UNKNOWN"
        final_reject_reason = "UNKNOWN"

    original_stake = _first(payload, "original_stake", default="")
    stake = _first(payload, "stake", "stake_units", default="")
    selection = _first(payload, "selection", "selection_name", "selection_raw", default="")
    audit = {
        "run_group_id": run_group_id or _first(payload, "run_group_id", default=""),
        "run_id": run_id or _first(payload, "run_id", "source_run_id", default=""),
        "config_name": getattr(runtime_config, "name", None) or _first(payload, "config_name", "strategy_config_name", default=""),
        "ledger_path": ledger_path or _first(payload, "ledger_path", default=""),
        "source_snapshot_id": source_snapshot_id or _first(payload, "source_snapshot_id", default=""),
        "match_datetime": _first(payload, "match_datetime", default=""),
        "league": _first(payload, "league", default=""),
        "home_team": _first(payload, "home_team", default=""),
        "away_team": _first(payload, "away_team", default=""),
        "market_type": _first(payload, "market_type", default=""),
        "market_family": _first(payload, "market_family", default="") or infer_market_family(payload),
        "selection": selection,
        "selection_normalized": _selection_normalized(payload),
        "line": _first(payload, "line", default=""),
        "odd_entrada": _first(payload, "odd_entrada", "odd", default=""),
        "odd": _first(payload, "odd", "odd_entrada", default=""),
        "ev_percent": _first(payload, "ev_percent", "ev_percent_adjusted", "ev_percent_base", default=""),
        "confidence_score": _first(payload, "confidence_score", default=""),
        "entry_quality_score": _first(payload, "entry_quality_score", default=""),
        "original_stake": original_stake,
        "stake": stake,
        "market_filter_status": market_filter_status,
        "market_filter_reason": market_filter_reason,
        "odd_policy_status": odd_policy_status,
        "odd_policy_reason": odd_policy_reason,
        "ev_policy_status": ev_policy_status,
        "ev_policy_reason": ev_policy_reason,
        "market_exception_applied": bool(market_exception_applied),
        "market_exception_reason": market_exception_reason if market_exception_applied else "",
        "side_rule_status": side_rule_status,
        "side_rule_reason": side_rule_reason,
        "side_rule_evaluation": side_rule_evaluation,
        "sport_sense_status": sport_sense_status,
        "sport_sense_reason": sport_sense_reason,
        "sport_sense_evaluation": sport_sense_evaluation,
        "team_role": _first(payload, "team_role", default="unknown" if reached_profile_policy else "not_applicable"),
        "team_role_source": _first(payload, "team_role_source", default="unknown" if reached_profile_policy else "not_applicable"),
        "stake_policy_applied": stake_policy_status,
        "stake_policy_reason": stake_policy_reason or "UNKNOWN",
        "portfolio_status": portfolio_status,
        "portfolio_reason": portfolio_reason,
        "final_selected": bool(final_selected),
        "final_reject_reason": final_reject_reason,
    }
    return {column: audit.get(column, "") for column in AUDIT_COLS}


def empty_candidate_audit() -> pd.DataFrame:
    return pd.DataFrame(columns=AUDIT_COLS)


def build_candidate_audit(
    *,
    df_raw_candidates: pd.DataFrame,
    df_candidates: pd.DataFrame,
    df_blocked_candidates: pd.DataFrame,
    df_profile_policy_blocked: pd.DataFrame,
    df_portfolio_rejected: pd.DataFrame,
    df_final: pd.DataFrame,
    runtime_config: Any,
    run_id: str,
    run_group_id: str | None = None,
    ledger_path: str | None = None,
    source_snapshot_id: str | None = None,
) -> pd.DataFrame:
    if not isinstance(df_raw_candidates, pd.DataFrame) or df_raw_candidates.empty:
        return empty_candidate_audit()

    evaluated_raw_rows = _evaluate_raw_candidate_records(df_raw_candidates)
    raw_match_keys_by_bet_id: dict[str, set[tuple[str, str, str, str, str]]] = {}
    for raw, _eval_meta in evaluated_raw_rows:
        raw_match_keys_by_bet_id.setdefault(_candidate_bet_id(raw), set()).add(_candidate_match_key(raw))
    ambiguous_bet_ids = {
        bet_id
        for bet_id, match_keys in raw_match_keys_by_bet_id.items()
        if len(match_keys) > 1
    }
    approved_index = _stage_index(df_candidates)
    blocked_index = _stage_index(df_blocked_candidates)
    profile_blocked_index = _stage_index(df_profile_policy_blocked)
    portfolio_rejected_index = _stage_index(df_portfolio_rejected)
    final_index = _stage_index(df_final)

    rows: list[dict[str, Any]] = []
    for raw, eval_meta in evaluated_raw_rows:
        bet_id = _candidate_bet_id(raw)
        raw["bet_id"] = bet_id
        allow_fallback = bet_id not in ambiguous_bet_ids
        final_candidate = _pop_stage(final_index, raw, allow_bet_id_fallback=allow_fallback)
        portfolio_rejected = None if final_candidate is not None else _pop_stage(portfolio_rejected_index, raw, allow_bet_id_fallback=allow_fallback)
        profile_blocked = None if final_candidate is not None or portfolio_rejected is not None else _pop_stage(profile_blocked_index, raw, allow_bet_id_fallback=allow_fallback)
        blocked_candidate = None if any(item is not None for item in (final_candidate, portfolio_rejected, profile_blocked)) else _pop_stage(blocked_index, raw, allow_bet_id_fallback=allow_fallback)
        approved_candidate = _pop_stage(approved_index, raw, allow_bet_id_fallback=allow_fallback) if eval_meta.get("accepted") else None
        payload: dict[str, Any] = {}
        for part in (
            raw,
            eval_meta.get("payload"),
            blocked_candidate,
            approved_candidate,
            profile_blocked,
            portfolio_rejected,
            final_candidate,
        ):
            if isinstance(part, dict):
                payload.update(part)
        rows.append(
            _audit_row(
                raw=raw,
                eval_meta=eval_meta,
                payload=payload,
                runtime_config=runtime_config,
                run_id=run_id,
                run_group_id=run_group_id,
                ledger_path=ledger_path,
                source_snapshot_id=source_snapshot_id,
                approved_candidate=approved_candidate,
                profile_blocked=profile_blocked,
                portfolio_rejected=portfolio_rejected,
                final_candidate=final_candidate,
            )
        )
    return pd.DataFrame(rows, columns=AUDIT_COLS)


def write_candidate_audit(df_candidate_audit: pd.DataFrame, candidate_audit_file: str | Path) -> Path:
    path = Path(candidate_audit_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df_candidate_audit.copy() if isinstance(df_candidate_audit, pd.DataFrame) else empty_candidate_audit()
    for column in AUDIT_COLS:
        if column not in df.columns:
            df[column] = pd.NA
    df[AUDIT_COLS].to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def build_candidate_audit_summary(df_candidate_audit: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df_candidate_audit, pd.DataFrame) or df_candidate_audit.empty:
        return pd.DataFrame(columns=[*SUMMARY_GROUP_COLS, "candidate_count"])
    df = df_candidate_audit.copy()
    for column in SUMMARY_GROUP_COLS:
        if column not in df.columns:
            df[column] = "unknown"
        df[column] = df[column].fillna("unknown").astype(str)
    return (
        df.groupby(SUMMARY_GROUP_COLS, dropna=False)
        .size()
        .reset_index(name="candidate_count")
        .sort_values(SUMMARY_GROUP_COLS)
        .reset_index(drop=True)
    )


def _candidate_audit_files(output_dir: Path, run_group_id: str, run_date: str | None = None) -> list[Path]:
    if run_date:
        roots = [output_dir / run_date]
    elif output_dir.exists():
        roots = [path for path in output_dir.iterdir() if path.is_dir()]
    else:
        roots = []
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(root.glob(f"{run_group_id}_*/candidate_audit.csv"))
    return sorted(path for path in files if path.parent.name != run_group_id and not path.parent.name.endswith("_source"))


def candidate_audit_summary_path(output_dir: Path, run_group_id: str, run_date: str | None = None) -> Path:
    if run_date:
        return output_dir / run_date / run_group_id / "candidate_audit_summary.csv"
    return output_dir / run_group_id / "candidate_audit_summary.csv"


def write_candidate_audit_summary_for_group(
    *,
    output_dir: str | Path,
    run_group_id: str,
    run_date: str | None = None,
    source_snapshot_id: str | None = None,
) -> Path:
    output_root = Path(output_dir)
    files = _candidate_audit_files(output_root, run_group_id, run_date)
    frames = [pd.read_csv(path, sep=";") for path in files]
    combined = pd.concat(frames, ignore_index=True) if frames else empty_candidate_audit()
    summary = build_candidate_audit_summary(combined)
    summary_path = candidate_audit_summary_path(output_root, run_group_id, run_date)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False, sep=";", encoding="utf-8-sig")
    save_manifest(
        summary_path.parent,
        build_manifest(
            run_id=run_group_id,
            target_date=run_date or "",
            run_dir=summary_path.parent,
            status="candidate_audit_summary_completed",
            run_mode="analysis_batch_group",
            run_group_id=run_group_id,
            source_snapshot_id=source_snapshot_id,
            candidate_audit_summary_file=str(summary_path),
            candidate_audit_summary_rows=len(summary),
            candidate_audit_rows=len(combined),
            candidate_audit_files=[str(path) for path in files],
        ),
    )
    return summary_path


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera resumo da auditoria de candidatos para um run_group.")
    parser.add_argument("--run-group-id", required=True)
    parser.add_argument("--run-date")
    parser.add_argument("--source-snapshot-id")
    parser.add_argument("--output-dir", default="data/runs")
    args = parser.parse_args(list(argv) if argv is not None else None)
    path = write_candidate_audit_summary_for_group(
        output_dir=args.output_dir,
        run_group_id=args.run_group_id,
        run_date=args.run_date,
        source_snapshot_id=args.source_snapshot_id,
    )
    print(f"[+] Candidate audit summary salvo: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
