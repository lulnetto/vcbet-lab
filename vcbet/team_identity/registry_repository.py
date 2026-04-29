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
    "fotmob_team_name",
    "fotmob_team_id",
    "fotmob_short_name",
    "xg_provider_preferred",
    "canonical_team_name",
]

_LEGACY_OPTIONAL_COLUMNS = [
    "fotmob_team_name",
    "fotmob_team_id",
    "fotmob_short_name",
    "xg_provider_preferred",
    "canonical_team_name",
]


def read_registry(path: str | Path = DEFAULT_REGISTRY_FILE) -> list[RegistryAlias]:
    registry_path = Path(path)
    if not registry_path.exists():
        return []
    with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        rows = []
        for row in reader:
            kwargs: dict[str, str] = {}
            for col in APPROVED_COLUMNS:
                if col in _LEGACY_OPTIONAL_COLUMNS and col not in (reader.fieldnames or []):
                    kwargs[col] = ""
                else:
                    kwargs[col] = str(row.get(col, "") or "")
            rows.append(RegistryAlias(**kwargs))
        return rows


def registry_lookup(
    league: str,
    betano_name: str,
    candidates: Iterable[str],
    *,
    registry_file: str | Path = DEFAULT_REGISTRY_FILE,
    xg_source: str = "footystats",
    source_team_id_map: dict[str, str] | None = None,
) -> RegistryAlias | None:
    candidate_names = {normalize_team_name(name): name for name in candidates}
    betano_norm = normalize_team_name(betano_name)
    for row in read_registry(registry_file):
        if row.league != league or row.match_status != "MATCH_REGISTRY_APPROVED":
            continue
        if normalize_team_name(row.betano_name) != betano_norm:
            continue

        if xg_source == "fotmob":
            # 1. fotmob_team_id match (preferred)
            if row.fotmob_team_id and source_team_id_map:
                for candidate_name, candidate_id in source_team_id_map.items():
                    if str(candidate_id) == str(row.fotmob_team_id):
                        return RegistryAlias(
                            league=row.league,
                            betano_name=row.betano_name,
                            betano_team_id=row.betano_team_id,
                            betano_url=row.betano_url,
                            footystats_name=candidate_name,
                            match_status=row.match_status,
                            match_confidence=row.match_confidence,
                            match_method=row.match_method,
                            approved_at=row.approved_at,
                            source=row.source,
                        )

            # 2. fotmob_team_name match
            if row.fotmob_team_name:
                canonical = candidate_names.get(normalize_team_name(row.fotmob_team_name))
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

            # 3. canonical_team_name match
            if row.canonical_team_name:
                canonical = candidate_names.get(normalize_team_name(row.canonical_team_name))
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

            # 4. Fallback to footystats_name for mixed registries
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
        else:
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


def safe_write_registry_rows(
    rows: list[dict[str, str]],
    registry_path: str | Path,
    fieldnames: list[str] | None = None,
) -> int:
    """Escreve rows no registry de forma atômica e segura.

    - Recusa lista vazia (não trunca registry acidentalmente).
    - Escreve primeiro em .tmp.
    - Valida que o .tmp tem header + pelo menos 1 linha.
    - Só então substitui o original via Path.replace().
    """
    if not rows:
        raise ValueError("safe_write_registry_rows recusou: rows está vazio. Registry não será truncado.")

    registry_path = Path(registry_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fieldnames or APPROVED_COLUMNS
    tmp_path = registry_path.with_suffix(registry_path.suffix + ".tmp")

    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fieldnames,
            delimiter=";",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    # Validar que o .tmp tem conteúdo mínimo (header + 1 linha)
    with tmp_path.open("r", newline="", encoding="utf-8") as fh:
        lines = list(fh)
    if len(lines) < 2:
        raise ValueError(
            f"safe_write_registry_rows recusou: arquivo temporário {tmp_path} tem apenas {len(lines)} linha(s). "
            "Registry não será substituído."
        )

    tmp_path.replace(registry_path)
    return len(rows)


def _is_manual_ui_approved(row: RegistryAlias) -> bool:
    """Entradas aprovadas manualmente pela UI podem não ter betano_team_id/betano_url."""
    if row.match_status != "MATCH_REGISTRY_APPROVED":
        return False
    if not row.league or not row.betano_name:
        return False
    return row.source == "ui_review" or row.match_method in {"registry_review", "manual_override"}


def write_registry_aliases(rows: list[RegistryAlias], path: str | Path = DEFAULT_REGISTRY_FILE) -> tuple[int, int]:
    registry_path = Path(path)
    existing = [
        row for row in read_registry(registry_path)
        if is_valid_betano_team_identity(row.betano_name, row.betano_team_id, row.betano_url)
        or _is_manual_ui_approved(row)
    ]
    by_key = {
        registry_alias_key(row.league, row.betano_team_id, row.betano_name): row
        for row in existing
    }
    added = 0

    for row in rows:
        if not is_valid_betano_team_identity(row.betano_name, row.betano_team_id, row.betano_url) and not _is_manual_ui_approved(row):
            continue

        key = registry_alias_key(row.league, row.betano_team_id, row.betano_name)
        if key in by_key:
            continue

        by_key[key] = row
        added += 1

    output = sorted(by_key.values(), key=lambda item: (item.league, normalize_team_name(item.betano_name)))
    dict_rows = [asdict(row) for row in output]
    safe_write_registry_rows(dict_rows, registry_path, fieldnames=APPROVED_COLUMNS)
    return added, len(output)
