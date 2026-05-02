from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from vcbet.team_identity.registry_repository import DEFAULT_REGISTRY_FILE, read_registry, registry_alias_key
from vcbet.team_identity.scoring import (
    ReviewAlias,
    is_valid_betano_team_identity,
    normalize_team_name,
)


DEFAULT_REVIEW_FILE = Path("data/team_registry/alias_review_pending.csv")

REVIEW_COLUMNS = [
    "league",
    "betano_name",
    "betano_team_id",
    "betano_url",
    "suggested_footystats_name",
    "suggested_fotmob_name",
    "suggested_fotmob_team_id",
    "top_score",
    "match_confidence",
    "match_method",
    "review_reason",
    "ambiguous_options",
    "status",
    "source",
    "run_id",
    "event_url",
    "created_at",
    "updated_at",
]


def _is_approved_registry_row(row: Any) -> bool:
    if row.match_status != "MATCH_REGISTRY_APPROVED":
        return False
    if is_valid_betano_team_identity(row.betano_name, row.betano_team_id, row.betano_url):
        return True
    return bool(
        row.league
        and row.betano_name
        and (row.source == "ui_review" or row.match_method in {"registry_review", "manual_override"})
    )


def write_review_aliases(
    rows: list[ReviewAlias],
    path: str | Path = DEFAULT_REVIEW_FILE,
    *,
    approved_path: str | Path = DEFAULT_REGISTRY_FILE,
    synced_leagues: Iterable[str] | None = None,
) -> int:
    review_path = Path(path)
    review_path.parent.mkdir(parents=True, exist_ok=True)

    synced = set(synced_leagues or [])

    approved_keys: set[tuple[str, str]] = set()
    approved_file = Path(approved_path)
    if approved_file.exists():
        for row in read_registry(approved_file):
            if not _is_approved_registry_row(row):
                continue
            approved_keys.add(registry_alias_key(row.league, row.betano_team_id, row.betano_name))

    incoming: dict[tuple[str, str], ReviewAlias] = {}
    for row in rows:
        key = registry_alias_key(row.league, row.betano_team_id, row.betano_name)
        if key not in approved_keys:
            incoming[key] = row

    existing: dict[tuple[str, str], ReviewAlias] = {}
    if review_path.exists():
        with review_path.open("r", newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                item = ReviewAlias(**{col: str(row.get(col, "") or "") for col in REVIEW_COLUMNS})
                key = registry_alias_key(item.league, item.betano_team_id, item.betano_name)

                if key in approved_keys:
                    continue

                if synced and item.league in synced and key not in incoming:
                    continue

                existing[key] = item

    existing.update(incoming)

    with review_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in sorted(existing.values(), key=lambda item: (item.league, normalize_team_name(item.betano_name))):
            writer.writerow(asdict(row))

    return len(incoming)


def upsert_pending_to_functional_file(
    pending_rows: list[Any],
    path: str | Path = DEFAULT_REVIEW_FILE,
) -> int:
    """Converte PendingAliasRow (debug) para ReviewAlias e upserta no arquivo funcional."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    review_aliases: list[ReviewAlias] = []
    for row in pending_rows:
        score = str(getattr(row, "score", "") or "")
        match_confidence = str(getattr(row, "match_confidence", "") or "")
        if not match_confidence and score:
            try:
                match_confidence = f"{float(score) / 100:.4f}"
            except ValueError:
                match_confidence = ""
        match_status = str(getattr(row, "match_status", "") or "")
        registry_reason = str(getattr(row, "registry_reason", "") or "")
        review_reason = str(getattr(row, "review_reason", "") or "")
        if not review_reason:
            review_reason = f"{match_status}: {registry_reason}".strip(": ")
        review_aliases.append(
            ReviewAlias(
                league=str(row.league),
                betano_name=str(row.source_name),
                betano_team_id="",
                betano_url="",
                suggested_footystats_name=str(row.suggestion or ""),
                suggested_fotmob_name=str(getattr(row, "suggested_fotmob_name", "") or ""),
                suggested_fotmob_team_id=str(getattr(row, "suggested_fotmob_team_id", "") or ""),
                top_score=score,
                match_confidence=match_confidence,
                match_method=str(getattr(row, "match_method", "") or match_status),
                review_reason=review_reason,
                ambiguous_options="",
                status="pending_review",
                source=str(getattr(row, "source", "") or "run_pipeline"),
                run_id=str(getattr(row, "run_id", "") or ""),
                event_url=str(getattr(row, "event_url", "") or ""),
                created_at=row.created_at or now,
                updated_at=str(getattr(row, "updated_at", "") or now),
            )
        )
    return write_review_aliases(review_aliases, path=path)
