#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vcbet.core.config_ligas import carregar_ligas, obter_meta_liga
from vcbet.core.team_registry import (
    DEFAULT_REGISTRY_FILE,
    DEFAULT_REVIEW_FILE,
    DEFAULT_SNAPSHOT_FILE,
    BetanoTeam,
    build_registry_matches,
    is_valid_betano_team_identity,
    normalize_team_name,
    parse_betano_standings_html_with_diagnostics,
    write_registry_aliases,
    write_review_aliases,
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def standings_url_for_league(league: str) -> str | None:
    meta = obter_meta_liga(league)
    if not meta or not meta.get("betano_path"):
        return None
    return urljoin("https://www.betano.bet.br", str(meta["betano_path"])) + "?bt=standings"


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "VCBet team-alias-sync/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def latest_xg_snapshot(root: Path) -> Path | None:
    candidates = sorted((root / "data" / "runs").glob("*/*/xg_snapshot.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_footystats_teams(root: Path, league: str, xg_file: str | None = None) -> list[str]:
    path = Path(xg_file) if xg_file else latest_xg_snapshot(root)
    if not path:
        return []
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return []
    df = pd.read_csv(path, sep=None, engine="python")
    if "league" not in df.columns or "team_name" not in df.columns:
        return []
    teams = df.loc[df["league"].astype(str) == league, "team_name"].dropna().astype(str).unique().tolist()
    return sorted(teams)


def load_betano_teams(args: argparse.Namespace, league: str) -> tuple[list[BetanoTeam], str, dict[str, object]]:
    if args.from_html:
        html_path = Path(args.from_html)
        html = html_path.read_text(encoding="utf-8", errors="replace")
        result = parse_betano_standings_html_with_diagnostics(html, league=league)
        return result.teams, str(html_path), {
            "raw_count": result.raw_count,
            "duplicate_count": result.duplicate_count,
            "duplicate_entries": result.duplicate_entries,
            "found_standings_rows": result.found_standings_rows,
        }
    url = args.url or standings_url_for_league(league)
    if not url:
        return [], "missing_betano_url", {"raw_count": 0, "duplicate_count": 0, "duplicate_entries": [], "found_standings_rows": False}
    html = fetch_html(url)
    result = parse_betano_standings_html_with_diagnostics(html, league=league)
    return result.teams, url, {
        "raw_count": result.raw_count,
        "duplicate_count": result.duplicate_count,
        "duplicate_entries": result.duplicate_entries,
        "found_standings_rows": result.found_standings_rows,
    }


def coverage_status(betano_teams: list[BetanoTeam], footystats_teams: list[str], parse_diagnostics: dict[str, object]) -> tuple[str, str]:
    if not parse_diagnostics.get("found_standings_rows"):
        return "blocked", "standings_not_found_or_not_rendered"
    valid = [team for team in betano_teams if is_valid_betano_team_identity(team.name, team.betano_team_id, team.betano_url)]
    if len(valid) != len(betano_teams):
        return "blocked", "invalid_betano_team_rows"
    if len(footystats_teams) >= 10 and len(betano_teams) < max(8, int(len(footystats_teams) * 0.70)):
        return "blocked", "failed_partial_coverage"
    if not betano_teams or not footystats_teams:
        return "blocked", "missing_team_universe"
    return "ok", "ok"


def coverage_diagnostics(
    betano_teams: list[BetanoTeam],
    footystats_teams: list[str],
    approved: list[object],
    review: list[object],
) -> dict[str, object]:
    matched_betano = {normalize_team_name(item.betano_name) for item in approved}
    matched_betano.update(
        normalize_team_name(item.betano_name)
        for item in review
        if getattr(item, "suggested_footystats_name", "")
    )
    matched_footystats = {normalize_team_name(item.footystats_name) for item in approved}
    matched_footystats.update(
        normalize_team_name(item.suggested_footystats_name)
        for item in review
        if getattr(item, "suggested_footystats_name", "")
    )
    return {
        "total_betano": len(betano_teams),
        "total_footystats": len(footystats_teams),
        "matched_count": len(matched_betano),
        "auto_count": len(approved),
        "review_count": len(review),
        "footystats_without_betano_candidate": [
            name for name in footystats_teams if normalize_team_name(name) not in matched_footystats
        ],
        "betano_without_footystats_candidate": [
            team.name for team in betano_teams if normalize_team_name(team.name) not in matched_betano
        ],
    }


def sync_league(args: argparse.Namespace, league: str, root: Path | None = None) -> dict[str, object]:
    root = root or project_root()
    betano_teams, source, parse_diagnostics = load_betano_teams(args, league)
    footystats_teams = load_footystats_teams(root, league, args.xg_file)
    approved, review = build_registry_matches(
        betano_teams,
        footystats_teams,
        threshold=args.threshold,
        margin=args.margin,
        source=source,
    )
    sync_status, sync_coverage_status = coverage_status(betano_teams, footystats_teams, parse_diagnostics)
    snapshot = {
        "league": league,
        "source": source,
        "betano_teams": [team.__dict__ for team in betano_teams],
        "footystats_teams": footystats_teams,
        "approved_count": len(approved),
        "review_count": len(review),
        "approved_aliases": [item.__dict__ for item in approved],
        "review_aliases": [item.__dict__ for item in review],
        "parse_diagnostics": parse_diagnostics,
        "coverage": coverage_diagnostics(betano_teams, footystats_teams, approved, review),
        "status": sync_status,
        "coverage_status": sync_coverage_status,
    }
    if not args.dry_run and sync_status == "ok":
        snapshot_path = root / DEFAULT_SNAPSHOT_FILE
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        added, total = write_registry_aliases(approved, root / DEFAULT_REGISTRY_FILE)
        review_written = write_review_aliases(review, root / DEFAULT_REVIEW_FILE)
    else:
        added, total, review_written = 0, 0, 0
    return {
        **snapshot,
        "registry_added": added,
        "registry_total": total,
        "review_written": review_written,
        "dry_run": args.dry_run,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sincroniza aliases Betano ↔ FootyStats por liga.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--league", help="Nome da liga em ligas.json, ex: Bundesliga")
    scope.add_argument("--all", action="store_true", help="Sincroniza todas as ligas ativas com Betano/FootyStats")
    parser.add_argument("--from-html", help="HTML salvo da página Betano standings")
    parser.add_argument("--url", help="URL Betano standings explícita")
    parser.add_argument("--xg-file", help="Snapshot FootyStats/xG alternativo")
    parser.add_argument("--dry-run", action="store_true", help="Mostra resultados sem gravar CSVs")
    parser.add_argument("--verbose", action="store_true", help="Imprime times extraídos e candidatos de revisão")
    parser.add_argument("--debug-output", action="store_true", help="Alias de --verbose para diagnósticos")
    parser.add_argument("--threshold", type=float, default=0.94)
    parser.add_argument("--margin", type=float, default=0.08)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all and args.from_html:
        raise SystemExit("--from-html precisa ser usado com --league para evitar aplicar um HTML a várias ligas.")
    leagues = [args.league] if args.league else [
        item["nome"] for item in carregar_ligas() if item.get("betano_path") and item.get("footystats_url")
    ]
    summaries = []
    for league in leagues:
        try:
            summary = sync_league(args, league)
            summaries.append(summary)
            print(
                f"[{summary.get('status', 'ok')}] {league}: betano={len(summary['betano_teams'])} "
                f"footystats={len(summary['footystats_teams'])} "
                f"auto={summary['approved_count']} review={summary['review_count']} "
                f"coverage={summary.get('coverage_status', 'ok')} dry_run={summary['dry_run']}"
            )
            if args.verbose or args.debug_output:
                coverage = summary["coverage"]
                parse_diagnostics = summary["parse_diagnostics"]
                print("[coverage]")
                print(f"  total_betano={coverage['total_betano']}")
                print(f"  total_footystats={coverage['total_footystats']}")
                print(f"  matched={coverage['matched_count']} auto={coverage['auto_count']} review={coverage['review_count']}")
                print(
                    f"  betano_raw={parse_diagnostics['raw_count']} "
                    f"deduped={parse_diagnostics['duplicate_count']}"
                )
                print("[footystats_without_betano_candidate]")
                for name in coverage["footystats_without_betano_candidate"]:
                    print(f"  - {name}")
                print("[betano_without_footystats_candidate]")
                for name in coverage["betano_without_footystats_candidate"]:
                    print(f"  - {name}")
                print("[deduped_betano_entries]")
                for item in parse_diagnostics["duplicate_entries"]:
                    print(f"  - {item}")
                print("[betano_teams]")
                for item in summary["betano_teams"]:
                    print(f"  - {item.get('name')} | id={item.get('betano_team_id')} | url={item.get('betano_url')}")
                print("[review_candidates]")
                for item in summary["review_aliases"]:
                    print(
                        f"  - {item.get('betano_name')} -> {item.get('suggested_footystats_name')} "
                        f"score={item.get('top_score')} reason={item.get('review_reason')} "
                        f"options={item.get('ambiguous_options')}"
                    )
        except Exception as exc:
            print(f"[erro] {league}: {exc}")
    total_auto = sum(int(item["approved_count"]) for item in summaries)
    total_review = sum(int(item["review_count"]) for item in summaries)
    print(f"[summary] leagues={len(summaries)} auto_approved={total_auto} review={total_review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
