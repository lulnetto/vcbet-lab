#!/usr/bin/env python3
"""Atualiza aliases conhecidos no registro aprovado com FotMob IDs a partir do snapshot xG mais recente."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from vcbet.team_identity.registry_repository import (
    APPROVED_COLUMNS,
    DEFAULT_REGISTRY_FILE,
    safe_write_registry_rows,
)
from vcbet.team_identity.scoring import normalize_team_name


KNOWN_ALIASES = {
    ("La Liga", "Athletic Bilbao"): {"footystats_name": "Athletic Club", "fotmob_team_name": "Athletic Club"},
    ("Segunda División", "CD Castellón"): {"footystats_name": "Castellon", "fotmob_team_name": "Castellon"},
    ("Brasileirão Série A", "Athletico-PR"): {"footystats_name": "Athletico Paranaense", "fotmob_team_name": "Athletico Paranaense"},
}


def _find_latest_xg_snapshot(project_root: Path) -> Path | None:
    xg_dir = project_root / "data" / "xg"
    if not xg_dir.exists():
        return None
    dirs = sorted([d for d in xg_dir.iterdir() if d.is_dir()], reverse=True)
    for d in dirs:
        snapshot = d / "xg_snapshot.csv"
        if snapshot.exists():
            return snapshot
    return None


def _load_fotmob_ids(snapshot_path: Path) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    with snapshot_path.open("r", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            league = str(row.get("league", "")).strip()
            team = str(row.get("team_name", "")).strip()
            if not league or not team:
                continue
            key = (league, normalize_team_name(team))
            result[key] = {
                "fotmob_team_id": str(row.get("source_team_id", "")).strip(),
                "fotmob_team_name": team,
                "fotmob_short_name": str(row.get("short_name", "")).strip(),
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Atualiza aliases conhecidos com FotMob IDs")
    parser.add_argument("--project-root", default=".", help="Raiz do projeto")
    parser.add_argument("--snapshot", default=None, help="Caminho do xG snapshot (padrão: mais recente)")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    snapshot_path = Path(args.snapshot) if args.snapshot else _find_latest_xg_snapshot(project_root)
    if not snapshot_path:
        print("[ERRO] Nenhum snapshot xG encontrado.")
        return 1

    print(f"[INFO] Usando snapshot: {snapshot_path}")
    fotmob_map = _load_fotmob_ids(snapshot_path)

    registry_path = project_root / DEFAULT_REGISTRY_FILE
    with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    updated = 0
    for row in rows:
        league = str(row.get("league", "")).strip()
        betano_name = str(row.get("betano_name", "")).strip()
        key = (league, betano_name)

        if key not in KNOWN_ALIASES:
            continue

        info = KNOWN_ALIASES[key]
        fotmob_info = fotmob_map.get((league, normalize_team_name(info["fotmob_team_name"])), {})
        if not fotmob_info:
            fotmob_info = fotmob_map.get((league, normalize_team_name(str(row.get("footystats_name", "")).strip())), {})

        fotmob_team_id = fotmob_info.get("fotmob_team_id", "")
        fotmob_team_name = fotmob_info.get("fotmob_team_name", info["footystats_name"])
        fotmob_short_name = fotmob_info.get("fotmob_short_name", "")

        if row.get("fotmob_team_id") == fotmob_team_id and row.get("fotmob_team_name") == fotmob_team_name:
            print(f"[SKIP] Já atualizado: {league} | {betano_name}")
            continue

        row["footystats_name"] = info["footystats_name"]
        row["match_method"] = "known_alias_cli"
        row["source"] = "known_alias_cli"
        row["fotmob_team_name"] = fotmob_team_name
        row["fotmob_team_id"] = fotmob_team_id
        row["fotmob_short_name"] = fotmob_short_name
        row["xg_provider_preferred"] = "fotmob"
        row["canonical_team_name"] = info["footystats_name"]
        updated += 1
        print(
            f"[UPDATE] {league} | {betano_name} -> {info['footystats_name']} "
            f"(fotmob_id={fotmob_team_id}, fotmob_name={fotmob_team_name})"
        )

    if updated:
        safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)
        print(f"[OK] {updated} alias(s) atualizado(s). Total no registro: {len(rows)}")
    else:
        print("[OK] Nenhum alias precisa de atualização.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
