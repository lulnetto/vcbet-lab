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
    parse_betano_standings_html,
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


def load_betano_teams(args: argparse.Namespace, league: str) -> tuple[list[BetanoTeam], str]:
    if args.from_html:
        html_path = Path(args.from_html)
        html = html_path.read_text(encoding="utf-8", errors="replace")
        return parse_betano_standings_html(html, league=league), str(html_path)
    url = args.url or standings_url_for_league(league)
    if not url:
        return [], "missing_betano_url"
    html = fetch_html(url)
    return parse_betano_standings_html(html, league=league), url


def sync_league(args: argparse.Namespace, league: str) -> dict[str, object]:
    root = project_root()
    betano_teams, source = load_betano_teams(args, league)
    footystats_teams = load_footystats_teams(root, league, args.xg_file)
    approved, review = build_registry_matches(
        betano_teams,
        footystats_teams,
        threshold=args.threshold,
        margin=args.margin,
        source=source,
    )
    snapshot = {
        "league": league,
        "source": source,
        "betano_teams": [team.__dict__ for team in betano_teams],
        "footystats_teams": footystats_teams,
        "approved_count": len(approved),
        "review_count": len(review),
    }
    if not args.dry_run:
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
                f"[ok] {league}: betano={len(summary['betano_teams'])} "
                f"footystats={len(summary['footystats_teams'])} "
                f"auto={summary['approved_count']} review={summary['review_count']} "
                f"dry_run={summary['dry_run']}"
            )
        except Exception as exc:
            print(f"[erro] {league}: {exc}")
    total_auto = sum(int(item["approved_count"]) for item in summaries)
    total_review = sum(int(item["review_count"]) for item in summaries)
    print(f"[summary] leagues={len(summaries)} auto_approved={total_auto} review={total_review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
