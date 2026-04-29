#!/usr/bin/env python3
"""Gera diagnóstico de pareamento Betano ↔ FotMob para uma liga.

Uso:
    python scripts/diagnose_fotmob_registry.py --league "MLS"

Saída:
    Imprime CSV com colunas:
    league;betano_team_name;suggested_fotmob_team_name;suggested_fotmob_team_id;score;status
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from vcbet.collectors.fotmob_client import FotMobClient
from vcbet.collectors.fotmob_xg_collector import parse_fotmob_league_xg
from vcbet.core.config_ligas import obter_meta_liga
from vcbet.team_identity.scoring import (
    BetanoTeam,
    normalize_team_name,
    parse_betano_standings_html,
    score_team_match,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnóstico de registry FotMob por liga")
    parser.add_argument("--league", required=True, help="Nome da liga em ligas.json")
    parser.add_argument("--output", default="-", help="Arquivo de saída (- para stdout)")
    return parser.parse_args()


def fetch_betano_standings_html(betano_path: str) -> str:
    url = f"https://www.betano.bet.br{betano_path}?bt=standings"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def main() -> int:
    args = parse_args()
    league = args.league

    meta = obter_meta_liga(league)
    if not meta:
        print(f"[erro] Liga '{league}' não encontrada em ligas.json", file=sys.stderr)
        return 1

    league_id = meta.get("fotmob_league_id")
    ccode3 = meta.get("fotmob_ccode3")
    betano_path = meta.get("betano_path")
    if not league_id or not ccode3:
        print(f"[erro] Liga '{league}' sem fotmob_league_id/ccode3", file=sys.stderr)
        return 1

    # Fetch FotMob xG
    client = FotMobClient()
    result = client.fetch_league_data(league_id=int(league_id), ccode3=str(ccode3))
    if not result.ok or result.json_data is None:
        print(f"[erro] FotMob fetch falhou: {result.error}", file=sys.stderr)
        return 1

    df_xg = parse_fotmob_league_xg(
        league_name=league,
        league_id=int(league_id),
        ccode3=str(ccode3),
        json_data=result.json_data,
        run_id="diagnostic",
        collected_at="",
    )
    fotmob_candidates = df_xg["team_name"].tolist()
    fotmob_id_map = {
        str(row["team_name"]): str(row.get("source_team_id", ""))
        for _, row in df_xg.iterrows()
    }

    # Fetch Betano teams
    betano_teams: list[BetanoTeam] = []
    if betano_path:
        try:
            html = fetch_betano_standings_html(betano_path)
            betano_teams = parse_betano_standings_html(html, league=league)
        except Exception as exc:
            print(f"[aviso] Falha ao buscar standings Betano: {exc}", file=sys.stderr)

    if not betano_teams:
        print(f"[aviso] Nenhum time Betano encontrado; imprimindo apenas candidatos FotMob", file=sys.stderr)

    rows: list[dict] = []
    for team in betano_teams:
        best = None
        best_score = 0.0
        for cand in fotmob_candidates:
            match = score_team_match(team.name, cand)
            if match.score > best_score:
                best_score = match.score
                best = cand

        fotmob_id = fotmob_id_map.get(best, "") if best else ""
        status = "approved" if best_score >= 0.94 else ("review" if best_score >= 0.75 else "blocked")
        rows.append({
            "league": league,
            "betano_team_name": team.name,
            "suggested_fotmob_team_name": best or "",
            "suggested_fotmob_team_id": fotmob_id,
            "score": f"{best_score:.4f}",
            "status": status,
        })

    output = sys.stdout if args.output == "-" else open(args.output, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        output,
        fieldnames=["league", "betano_team_name", "suggested_fotmob_team_name", "suggested_fotmob_team_id", "score", "status"],
        delimiter=";",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    if args.output != "-":
        output.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
