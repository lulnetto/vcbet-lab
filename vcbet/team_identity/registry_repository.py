from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from vcbet.team_identity.scoring import (
    RegistryAlias,
    is_valid_betano_team_identity,
    normalize_team_name,
)


DEFAULT_REGISTRY_FILE = Path("configs/team_registry/betano_footystats_aliases.csv")
DEFAULT_SNAPSHOT_FILE = Path("data/team_registry/betano_teams_snapshot.json")

APPROVED_COLUMNS = [
    "league",
    "betano_name",
    "betano_team_id",
    "betano_url",
    "footystats_name",
    "match_status",
    "match_confidence",
    "match_method",
    "approved_at",
    "source",
]


def read_registry(path: str | Path = DEFAULT_REGISTRY_FILE) -> list[RegistryAlias]:
    registry_path = Path(path)
    if not registry_path.exists():
        return []
    with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        rows = []
        for row in reader:
            rows.append(RegistryAlias(**{col: str(row.get(col, "") or "") for col in APPROVED_COLUMNS}))
        return rows


def registry_lookup(
    league: str,
    betano_name: str,
    candidates: Iterable[str],
    *,
    registry_file: str | Path = DEFAULT_REGISTRY_FILE,
) -> RegistryAlias | None:
    candidate_names = {normalize_team_name(name): name for name in candidates}
    betano_norm = normalize_team_name(betano_name)
    for row in read_registry(registry_file):
        if row.league != league or row.match_status != "MATCH_REGISTRY_APPROVED":
            continue
        if normalize_team_name(row.betano_name) != betano_norm:
            continue
        canonical = candidate_names.get(normalize_team_name(row.footystats_name))
        if canonical:
            return RegistryAlias(
                league=row.league,
                betano_name=row.betano_name,
                betano_team_id=row.betano_team_id,
                betano_url=row.betano_url,
                footystats_name=canonical,
                match_status=row.match_status,
                match_confidence=row.match_confidence,
                match_method=row.match_method,
                approved_at=row.approved_at,
                source=row.source,
            )
    return None


def registry_alias_key(league: str, betano_team_id: str, betano_name: str) -> tuple[str, str]:
    team_id = str(betano_team_id or "").strip()
    if team_id:
        return (league, f"id:{team_id}")
    return (league, f"name:{normalize_team_name(betano_name)}")


def write_registry_aliases(rows: list[RegistryAlias], path: str | Path = DEFAULT_REGISTRY_FILE) -> tuple[int, int]:
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = [
        row for row in read_registry(registry_path)
        if is_valid_betano_team_identity(row.betano_name, row.betano_team_id, row.betano_url)
    ]
    by_key = {
        registry_alias_key(row.league, row.betano_team_id, row.betano_name): row
        for row in existing
    }
    added = 0

    for row in rows:
        if not is_valid_betano_team_identity(row.betano_name, row.betano_team_id, row.betano_url):
            continue

        key = registry_alias_key(row.league, row.betano_team_id, row.betano_name)
        if key in by_key:
            continue

        by_key[key] = row
        added += 1

    output = sorted(by_key.values(), key=lambda item: (item.league, normalize_team_name(item.betano_name)))
    with registry_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=APPROVED_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in output:
            writer.writerow(asdict(row))
    return added, len(output)
