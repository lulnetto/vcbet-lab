from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["queued", "running", "success", "failed", "cancelled", "blocked", "interrupted"]
JobType = Literal["analysis", "closing_odds", "results_collection", "settlement", "results_settlement_cycle", "daily_run", "replay_run"]


class JobPhase(BaseModel):
    name: str
    status: JobStatus = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    command: list[str] = Field(default_factory=list)
    message: str | None = None


class JobRecord(BaseModel):
    id: str
    job_type: JobType
    status: JobStatus
    title: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    resource_key: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    phases: list[JobPhase] = Field(default_factory=list)
    log_path: str | None = None
    exit_code: int | None = None
    error: str | None = None
    command_preview: str | None = None


class AnalysisRequest(BaseModel):
    mode: Literal["full", "legacy"] = "full"
    date: str | None = None
    run_id: str | None = None
    odds_file: str | None = None
    xg_file: str | None = None
    alias_file: str = "alias_times.json"
    ledger_file: str = "data/history/bets_ledger.csv"
    output_dir: str = "data/runs"
    python_bin: str = "python3"
    json_output: bool = False
    debug: bool = False
    dry_run: bool = False
    config_file: str | None = None
    config_name: str | None = None
    xg_source: str = "fotmob"


class ClosingOddsRequest(BaseModel):
    ledger_file: str = "data/history/bets_ledger.csv"
    window_minutes: int = 60
    allow_past_minutes: int = 10
    all_pending: bool = False
    bet_ids: list[str] = Field(default_factory=list)
    python_bin: str = "python3"


class ResultsCollectionRequest(BaseModel):
    ledger_file: str = "data/history/bets_ledger.csv"
    output_file: str = "data/results/results_auto.csv"
    all_pending: bool = False
    grace_minutes: int = 110
    debug: bool = False
    debug_dir: str = "data/results/_debug"
    max_pages: int = 6
    source: str | None = None
    python_bin: str = "python3"


class SettlementRequest(BaseModel):
    ledger_file: str = "data/history/bets_ledger.csv"
    results_file: str = "data/results/results_auto.csv"
    overrides_file: str | None = None
    no_overrides: bool = False
    python_bin: str = "python3"


class ResultsSettlementRequest(BaseModel):
    ledger_file: str = "data/history/bets_ledger.csv"
    results_file: str = "data/results/results_auto.csv"
    overrides_file: str | None = None
    all_pending: bool = False
    results_grace_minutes: int = 110
    results_max_pages: int = 6
    results_source: str | None = None
    results_debug: bool = False
    no_overrides: bool = False
    python_bin: str = "python3"


class DailyRunRequest(BaseModel):
    date: str | None = None
    run_id: str | None = None
    ledger_file: str = "data/history/bets_ledger.csv"
    output_dir: str = "data/runs"
    alias_file: str = "alias_times.json"
    results_file: str = "data/results/results_auto.csv"
    overrides_file: str | None = None
    python_bin: str = "python3"
    json_output: bool = False
    debug: bool = False
    dry_run: bool = False
    closing_window_minutes: int = 60
    closing_allow_past_minutes: int = 10
    results_grace_minutes: int = 110
    results_max_pages: int = 6
    results_source: str | None = None
    skip_analysis: bool = False
    skip_closing_odds: bool = True
    skip_results_collection: bool = False
    skip_settlement: bool = False
    refresh_catalogs: bool = True
    config_file: str | None = None
    config_name: str | None = None
    xg_source: str = "fotmob"


class ReplayRunRequest(BaseModel):
    source_run_dir: str
    configs: list[str] = Field(default_factory=list)
    output_dir: str = "data/replays"
    alias_file: str = "alias_times.json"
    python_bin: str = "python3"
    evaluate_results: bool = False
    results_source: str | None = None
    results_grace_minutes: int = 110
    results_max_pages: int = 6
    results_debug: bool = False
    persist: bool = False


class AliasApprovalItem(BaseModel):
    row_id: str
    source_name: str
    target_name: str


class AliasApproveRequest(BaseModel):
    pending_file: str
    alias_file: str = "alias_times.json"
    approvals: list[AliasApprovalItem] = Field(default_factory=list)
    include_blocked: bool = True


class TeamRegistryAliasRequest(BaseModel):
    league: str
    betano_name: str
    betano_team_id: str = ""
    betano_url: str = ""
    suggested_footystats_name: str | None = None
    footystats_name: str | None = None
    canonical_xg_name: str | None = None
    xg_provider: str = "fotmob"
    top_score: str | None = None
    review_reason: str | None = None
    ambiguous_options: str | None = None
    status: str | None = None
    source: str | None = None
    match_confidence: str | None = None
    match_method: str | None = None
    coverage_status: str | None = None
    manual_override: bool = False
    manual_override_reason: str | None = None


class TeamRegistrySyncRequest(BaseModel):
    league: str
    source: Literal["configured_url", "saved_html"] = "configured_url"
    html_path: str | None = None
    xg_file: str | None = None
    threshold: float = 0.94
    margin: float = 0.08
    force_refresh_phase: bool = False
    debug_network: bool = False


class TeamRegistrySyncAllRequest(BaseModel):
    threshold: float = 0.94
    margin: float = 0.08


class ConfigInfo(BaseModel):
    name: str
    label: str
    description: str = ""
    path: str | None = None
    fingerprint: str | None = None


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    title: str


class HealthResponse(BaseModel):
    status: str
    project_root: str
    jobs_dir: str
    logs_dir: str
    now: datetime


class JobListResponse(BaseModel):
    items: list[JobRecord]
