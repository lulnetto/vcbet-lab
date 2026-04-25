#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vcbet.team_identity import sync_service as _sync


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
    parser.add_argument("--debug-network", action="store_true", help="Captura rede/DOM da Betano e grava artefato de debug")
    parser.add_argument("--force-refresh-phase", action="store_true", help="Redescobre phaseId da API Betano via Playwright")
    parser.add_argument("--threshold", type=float, default=0.94)
    parser.add_argument("--margin", type=float, default=0.08)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all and args.from_html:
        raise SystemExit("--from-html precisa ser usado com --league para evitar aplicar um HTML a várias ligas.")
    leagues = [args.league] if args.league else _sync.syncable_leagues()
    summaries = []
    for league in leagues:
        try:
            summary = _sync.sync_league(args, league)
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
                if parse_diagnostics.get("phase_id"):
                    print(
                        f"  phase_id={parse_diagnostics.get('phase_id')} "
                        f"title={parse_diagnostics.get('phase_title')} "
                        f"source=phaseStandings API"
                    )
                if parse_diagnostics.get("debug_artifact"):
                    print(f"  debug_artifact={parse_diagnostics.get('debug_artifact')}")
                if parse_diagnostics.get("error"):
                    print(f"  discovery_error={parse_diagnostics.get('error')}")
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


_sync.parse_args = parse_args
_sync.main = main

if __name__ != "__main__":
    sys.modules[__name__] = _sync

if __name__ == "__main__":
    raise SystemExit(main())
