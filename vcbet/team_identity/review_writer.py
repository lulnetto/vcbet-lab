from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

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
    "top_score",
    "review_reason",
    "ambiguous_options",
    "status",
    "source",
    "created_at",
    "updated_at",
]


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
            if row.match_status != "MATCH_REGISTRY_APPROVED":
                continue
            if not is_valid_betano_team_identity(row.betano_name, row.betano_team_id, row.betano_url):
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
