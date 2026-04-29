#!/usr/bin/env python3
"""Backfill conservador de FotMob IDs no registro aprovado a partir de snapshot xG."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from vcbet.team_identity.registry_repository import (
    APPROVED_COLUMNS,
    DEFAULT_REGISTRY_FILE,
    safe_write_registry_rows,
)
from vcbet.team_identity.scoring import normalize_team_name


@dataclass(frozen=True)
class FotMobTeam:
    league: str
    team_name: str
    short_name: str
    team_id: str


# Denylist: pares (league, betano_name) que NUNCA devem ser alterados pelo backfill automático.
# Apenas aprovação manual via approve_known_aliases.py pode tocar nestes.
DENYLIST: set[tuple[str, str]] = {
    ("Serie A", "Inter de Milão"),
    ("MLS", "Los Angeles Galaxy"),
    ("La Liga", "Athletic Bilbao"),
    ("Brasileirão Série A", "Athletico-PR"),
    ("Segunda División", "CD Castellón"),
}

REPORT_COLUMNS = [
    "league",
    "betano_name",
    "footystats_name",
    "canonical_team_name",
    "status",
    "matched_fotmob_team_name",
    "matched_fotmob_team_id",
    "candidate_count",
    "reason",
]


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


def _load_fotmob_lookup(snapshot_path: Path) -> dict[str, list[FotMobTeam]]:
    """Mapeia league -> lista de times FotMob."""
    result: dict[str, list[FotMobTeam]] = {}
    with snapshot_path.open("r", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            league = str(row.get("league", "")).strip()
            team_name = str(row.get("team_name", "")).strip()
            short_name = str(row.get("short_name", "")).strip()
            team_id = str(row.get("source_team_id", "")).strip()
            if not league or not team_name:
                continue
            result.setdefault(league, []).append(
                FotMobTeam(
                    league=league,
                    team_name=team_name,
                    short_name=short_name,
                    team_id=team_id,
                )
            )
    return result


def _normalize(value: str) -> str:
    return normalize_team_name(str(value or ""))


def _find_safe_matches(
    league: str,
    candidates: list[str],
    fotmob_teams: list[FotMobTeam],
) -> list[FotMobTeam]:
    """Retorna times FotMob que casam exatamente (normalizado) com algum candidate."""
    matches: list[FotMobTeam] = []
    seen_ids: set[str] = set()
    for team in fotmob_teams:
        team_name_norm = _normalize(team.team_name)
        short_norm = _normalize(team.short_name) if team.short_name else ""
        for cand in candidates:
            cand_norm = _normalize(cand)
            if not cand_norm:
                continue
            if cand_norm == team_name_norm or (short_norm and cand_norm == short_norm):
                if team.team_id not in seen_ids:
                    seen_ids.add(team.team_id)
                    matches.append(team)
                break
    return matches


def _evaluate_row(
    row: dict[str, str],
    fotmob_lookup: dict[str, list[FotMobTeam]],
) -> dict[str, str]:
    league = str(row.get("league", "")).strip()
    betano_name = str(row.get("betano_name", "")).strip()
    footystats_name = str(row.get("footystats_name", "")).strip()
    canonical = str(row.get("canonical_team_name", "")).strip()
    existing_fotmob_id = str(row.get("fotmob_team_id", "")).strip()
    existing_fotmob_name = str(row.get("fotmob_team_name", "")).strip()

    # Já preenchido
    if existing_fotmob_id and existing_fotmob_name:
        return {
            "league": league,
            "betano_name": betano_name,
            "footystats_name": footystats_name,
            "canonical_team_name": canonical,
            "status": "already_filled",
            "matched_fotmob_team_name": existing_fotmob_name,
            "matched_fotmob_team_id": existing_fotmob_id,
            "candidate_count": "0",
            "reason": "fotmob_already_present",
        }

    # Denylist
    if (league, betano_name) in DENYLIST:
        return {
            "league": league,
            "betano_name": betano_name,
            "footystats_name": footystats_name,
            "canonical_team_name": canonical,
            "status": "no_match",
            "matched_fotmob_team_name": "",
            "matched_fotmob_team_id": "",
            "candidate_count": "0",
            "reason": "denylist_protected",
        }

    fotmob_teams = fotmob_lookup.get(league, [])
    if not fotmob_teams:
        return {
            "league": league,
            "betano_name": betano_name,
            "footystats_name": footystats_name,
            "canonical_team_name": canonical,
            "status": "league_missing_in_xg",
            "matched_fotmob_team_name": "",
            "matched_fotmob_team_id": "",
            "candidate_count": "0",
            "reason": "league_not_in_snapshot",
        }

    # Candidatos em ordem de prioridade
    candidates = [c for c in [canonical, footystats_name, betano_name] if c]
    # Remover duplicatas preservando ordem
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    matches = _find_safe_matches(league, unique_candidates, fotmob_teams)

    if len(matches) == 1:
        match = matches[0]
        return {
            "league": league,
            "betano_name": betano_name,
            "footystats_name": footystats_name,
            "canonical_team_name": canonical,
            "status": "safe_exact",
            "matched_fotmob_team_name": match.team_name,
            "matched_fotmob_team_id": match.team_id,
            "candidate_count": str(len(unique_candidates)),
            "reason": f"exact_match_via_{_normalize(match.team_name)}",
        }

    if len(matches) > 1:
        names = ", ".join(m.team_name for m in matches)
        return {
            "league": league,
            "betano_name": betano_name,
            "footystats_name": footystats_name,
            "canonical_team_name": canonical,
            "status": "ambiguous_match",
            "matched_fotmob_team_name": names,
            "matched_fotmob_team_id": ", ".join(m.team_id for m in matches),
            "candidate_count": str(len(unique_candidates)),
            "reason": f"multiple_matches: {names}",
        }

    # Nenhum match exato. Verificar se há substring (apenas para classificação como unsafe)
    unsafe_hits = []
    for team in fotmob_teams:
        team_norm = _normalize(team.team_name)
        for cand in unique_candidates:
            cand_norm = _normalize(cand)
            if cand_norm in team_norm or team_norm in cand_norm:
                if cand_norm != team_norm:
                    unsafe_hits.append(team.team_name)
                    break

    if unsafe_hits:
        return {
            "league": league,
            "betano_name": betano_name,
            "footystats_name": footystats_name,
            "canonical_team_name": canonical,
            "status": "unsafe_partial_match",
            "matched_fotmob_team_name": ", ".join(unsafe_hits),
            "matched_fotmob_team_id": "",
            "candidate_count": str(len(unique_candidates)),
            "reason": f"partial_substring_only: {', '.join(unsafe_hits)}",
        }

    return {
        "league": league,
        "betano_name": betano_name,
        "footystats_name": footystats_name,
        "canonical_team_name": canonical,
        "status": "no_match",
        "matched_fotmob_team_name": "",
        "matched_fotmob_team_id": "",
        "candidate_count": str(len(unique_candidates)),
        "reason": "no_exact_or_safe_match",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill conservador de FotMob no registry")
    parser.add_argument("--project-root", default=".", help="Raiz do projeto")
    parser.add_argument("--registry", default=None, help="Caminho do registry CSV")
    parser.add_argument("--xg-file", default=None, help="Caminho do xG snapshot")
    parser.add_argument("--dry-run", action="store_true", help="Só gerar relatório, não alterar CSV")
    parser.add_argument("--apply", action="store_true", help="Aplicar apenas safe_exact")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    registry_path = Path(args.registry) if args.registry else project_root / DEFAULT_REGISTRY_FILE
    snapshot_path = Path(args.xg_file) if args.xg_file else _find_latest_xg_snapshot(project_root)

    if not snapshot_path:
        print("[ERRO] Nenhum snapshot xG encontrado.")
        return 1
    if not registry_path.exists():
        print(f"[ERRO] Registry não encontrado: {registry_path}")
        return 1

    print(f"[INFO] Snapshot: {snapshot_path}")
    print(f"[INFO] Registry: {registry_path}")

    fotmob_lookup = _load_fotmob_lookup(snapshot_path)

    with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    reports: list[dict[str, str]] = []
    to_apply: list[int] = []

    for idx, row in enumerate(rows):
        report = _evaluate_row(row, fotmob_lookup)
        reports.append(report)
        if report["status"] == "safe_exact":
            to_apply.append(idx)

    # Contagens
    counts: dict[str, int] = {}
    for r in reports:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(f"[INFO] safe_exact={counts.get('safe_exact', 0)}")
    print(f"[INFO] already_filled={counts.get('already_filled', 0)}")
    print(f"[INFO] ambiguous_match={counts.get('ambiguous_match', 0)}")
    print(f"[INFO] no_match={counts.get('no_match', 0)}")
    print(f"[INFO] unsafe_partial_match={counts.get('unsafe_partial_match', 0)}")
    print(f"[INFO] league_missing_in_xg={counts.get('league_missing_in_xg', 0)}")

    # Escrever relatório
    report_path = project_root / "data" / "team_registry" / "fotmob_registry_sync_report.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(reports)
    print(f"[INFO] Relatório: {report_path}")

    if args.dry_run:
        print("[DRY-RUN] Nenhuma alteração aplicada.")
        return 0

    if args.apply:
        applied = 0
        for idx in to_apply:
            report = reports[idx]
            row = rows[idx]
            row["fotmob_team_name"] = report["matched_fotmob_team_name"]
            row["fotmob_team_id"] = report["matched_fotmob_team_id"]
            row["fotmob_short_name"] = ""
            row["xg_provider_preferred"] = "fotmob"
            row["canonical_team_name"] = report["matched_fotmob_team_name"]
            applied += 1

        safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)
        print(f"[APPLY] {applied} registro(s) safe_exact aplicado(s).")
        return 0

    print("[INFO] Use --dry-run para simular ou --apply para aplicar safe_exact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
