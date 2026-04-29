from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import FastAPI


@dataclass(frozen=True)
class RouteContext:
    settings: Any
    manager: Any
    resource_key: Callable[..., Any]
    resolve_project_path: Callable[..., Any]
    read_text_csv: Callable[..., Any]
    write_text_csv: Callable[..., Any]
    read_csv_rows: Callable[..., Any]
    read_ledger_rows: Callable[..., Any]
    compact_pick_row: Callable[..., Any]
    alias_candidate_files: Callable[..., Any]
    normalize_alias_rows: Callable[..., Any]
    registry_approved_keys: Callable[..., Any]
    alias_file_payload: Callable[..., Any]
    project_rel: Callable[..., Any]
    read_jsonl_catalog: Callable[..., Any]
    refresh_catalog_if_needed: Callable[..., Any]
    run_label: Callable[..., Any]
    replay_label: Callable[..., Any]
    active_catalog_items: Callable[..., Any]
    safe_limit: Callable[..., Any]


def register_all_routes(app: FastAPI, ctx: RouteContext) -> None:
    from . import aliases, configs, dashboard, health, jobs, replays, runs, team_registry

    for route_module in (
        health,
        configs,
        runs,
        replays,
        aliases,
        team_registry,
        dashboard,
        jobs,
    ):
        route_module.register_routes(app, ctx)
