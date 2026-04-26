from __future__ import annotations

from dataclasses import fields, dataclass, field
from datetime import datetime
from typing import Any, Mapping


ScalarTime = str | datetime | None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        unequal_to_self = value != value
        if isinstance(unequal_to_self, bool) and unequal_to_self:
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "nan", "none", "<na>"}


def _clean_value(value: Any) -> Any:
    return None if _is_missing(value) else value


@dataclass(slots=True)
class NormalizedMarket:
    market_type: str
    scope: str
    side: str | None = None
    line: float | None = None
    target: str | None = None
    raw_market: str | None = None
    raw_selection: str | None = None


@dataclass(slots=True)
class OddsSnapshot:
    collected_at: ScalarTime
    kickoff: ScalarTime
    source: str
    markets: tuple[NormalizedMarket | Mapping[str, Any], ...] = ()
    source_run_id: str | None = None
    snapshot_file: str | None = None
    snapshot_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class XGSnapshot:
    collected_at: ScalarTime
    source: str
    team_rows: tuple[Mapping[str, Any], ...] = ()
    source_run_id: str | None = None
    snapshot_file: str | None = None
    snapshot_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PricingResult:
    prob_model: float
    fair_odds: float
    ev_percent: float
    lambda_home: float | None = None
    lambda_away: float | None = None
    lambda_val: float | None = None
    method: str | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LedgerAppendResult:
    appended: int = 0
    blocked: int = 0
    duplicate: int = 0
    provenance: Mapping[str, Any] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


@dataclass(slots=True)
class BetRecord:
    bet_id: str | None = None
    ledger_schema_version: str | None = None
    ledger_schema_status: str | None = None
    ledger_schema_missing_columns: str | None = None
    run_id: str | None = None
    config_name: str | None = None
    config_fingerprint: str | None = None
    config_source_path: str | None = None
    config_snapshot_file: str | None = None
    source_run_id: str | None = None
    source_snapshot_ref: str | None = None
    odds_source_run_id: str | None = None
    xg_source_run_id: str | None = None
    odds_snapshot_file: str | None = None
    xg_snapshot_file: str | None = None
    odds_snapshot_hash: str | None = None
    xg_snapshot_hash: str | None = None
    odds_snapshot_time: ScalarTime = None
    xg_asof: ScalarTime = None
    temporal_contract_version: str | None = None
    temporal_contract_status: str | None = None
    signal_version: str | None = None
    pipeline_version: str | None = None
    decision_timestamp: ScalarTime = None
    created_at: ScalarTime = None
    settled_at: ScalarTime = None
    league: str | None = None
    match_datetime: ScalarTime = None
    home_team: str | None = None
    away_team: str | None = None
    match_name: str | None = None
    market_raw: str | None = None
    event_url: str | None = None
    market_type: str | None = None
    market_scope: str | None = None
    target_team_role: str | None = None
    target_team_name: str | None = None
    side: str | None = None
    line: float | str | None = None
    selection_raw: str | None = None
    odd_entrada: float | str | None = None
    odd_justa: float | str | None = None
    prob_model: float | str | None = None
    ev_percent: float | str | None = None
    pricing_signal_type: str | None = None
    confidence_score: float | int | str | None = None
    confidence_score_type: str | None = None
    confidence_score_scale: str | None = None
    stake_units: float | str | None = None
    entry_reason: str | None = None
    risk_flags: str | None = None
    pick_safety_status: str | None = None
    candidate_stage: str | None = None
    safety_gate_reason: str | None = None
    decision_policy_status: str | None = None
    decision_reject_reason: str | None = None
    selection_policy_status: str | None = None
    selection_reject_reason: str | None = None
    portfolio_risk_status: str | None = None
    portfolio_risk_reason: str | None = None
    portfolio_exposure_scope: str | None = None
    portfolio_exposure_after: float | str | None = None
    ledger_portfolio_gate_status: str | None = None
    ledger_portfolio_gate_reason: str | None = None
    ledger_portfolio_related_bet_id: str | None = None
    ledger_portfolio_gate_details: str | None = None
    market_family: str | None = None
    bet_executed: str | None = None
    executed_at: ScalarTime = None
    odd_executada: float | str | None = None
    stake_units_executada: float | str | None = None
    execution_note: str | None = None
    auto_home_goals: int | float | str | None = None
    auto_away_goals: int | float | str | None = None
    auto_bet_status: str | None = None
    auto_settlement_status: str | None = None
    auto_odd_fechamento: float | str | None = None
    manual_home_goals: int | float | str | None = None
    manual_away_goals: int | float | str | None = None
    manual_bet_status: str | None = None
    manual_settlement_status: str | None = None
    manual_odd_fechamento: float | str | None = None
    final_home_goals: int | float | str | None = None
    final_away_goals: int | float | str | None = None
    final_bet_status: str | None = None
    final_settlement_status: str | None = None
    final_odd_fechamento: float | str | None = None
    closing_odd: float | str | None = None
    closing_bookmaker: str | None = None
    closing_snapshot_time: ScalarTime = None
    closing_source: str | None = None
    closing_update_status: str | None = None
    closing_update_error: str | None = None
    settlement_source: str | None = None
    settlement_confidence: str | None = None
    settlement_note: str | None = None
    sofascore_event_id: str | None = None
    source_event_id: str | None = None
    override_reason: str | None = None
    override_updated_at: ScalarTime = None
    result_units_model: float | str | None = None
    result_units_real: float | str | None = None
    extra_fields: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "BetRecord":
        known = {item.name for item in fields(cls)} - {"extra_fields"}
        values = {name: _clean_value(row.get(name)) for name in known if name in row}
        extra = {name: _clean_value(value) for name, value in row.items() if name not in known}
        if _is_missing(values.get("sofascore_event_id")) and not _is_missing(values.get("source_event_id")):
            values["sofascore_event_id"] = values["source_event_id"]
        if _is_missing(values.get("source_event_id")) and not _is_missing(values.get("sofascore_event_id")):
            values["source_event_id"] = values["sofascore_event_id"]
        return cls(**values, extra_fields=extra)

    def to_mapping(self, *, include_extra: bool = True) -> dict[str, Any]:
        payload = {item.name: getattr(self, item.name) for item in fields(self) if item.name != "extra_fields"}
        if include_extra:
            payload.update(dict(self.extra_fields))
        return payload
