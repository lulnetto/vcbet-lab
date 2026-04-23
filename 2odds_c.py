import argparse
import csv
import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup
from curl_cffi import requests

from config_ligas import carregar_ligas_betano
from market_normalizer import normalize_market_entry
from run_utils import build_manifest, ensure_run_dir, generate_run_id, save_manifest, update_manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class BetanoExtractor:
    def __init__(self):
        self.session = requests.Session(impersonate="chrome110")
        self.base_url = "https://www.betano.bet.br"
        self.session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9",
            }
        )

    def _extract_hydration_state(self, html_content: str) -> dict:
        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup.find_all("script"):
            if script.string and 'window["initial_state"]' in script.string:
                try:
                    raw_json = script.string.split('window["initial_state"]=', 1)[1].strip().rstrip(";")
                    return json.loads(raw_json)
                except Exception:
                    return {}
        return {}

    def get_match_urls_by_date(self, league_path: str, target_date: str) -> List[str]:
        url = f"{self.base_url}{league_path}"
        try:
            response = self.session.get(url, timeout=15)
            state = self._extract_hydration_state(response.text)
        except Exception as e:
            logging.error(f"Erro ao acessar a liga {league_path}: {e}")
            return []

        match_urls = []
        for block in state.get("data", {}).get("blocks", []):
            for event in block.get("events", []):
                start_time_ms = event.get("startTime")
                if not start_time_ms or "url" not in event:
                    continue

                event_date = datetime.fromtimestamp(start_time_ms / 1000).strftime("%Y-%m-%d")
                if event_date == target_date:
                    match_urls.append(event["url"])

        return list(set(match_urls))

    def extract_all_odds(self, match_path: str, min_odd: float, league_name: str, run_id: str) -> List[Dict]:
        event_url = f"{self.base_url}{match_path}" if match_path.startswith("/") else match_path
        url = f"{event_url}?bt=14"
        collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            response = self.session.get(url, timeout=10)
            state = self._extract_hydration_state(response.text)
        except Exception as e:
            logging.error(f"Erro ao acessar partida {url}: {e}")
            return []

        rows = []
        try:
            event_data = state["data"]["event"]
            match_name = event_data.get("name", "")
            home_team, away_team = split_match_name(match_name)
            start_time = datetime.fromtimestamp(event_data.get("startTime") / 1000).strftime("%Y-%m-%d %H:%M")

            for market in event_data.get("markets", []):
                market_name = market.get("name")
                if any(
                    key.lower() in market_name.lower()
                    for key in ["Total de Gols Mais/Menos", "Ambas equipes Marcam", "Total de gols", "Handicap Asiático"]
                ):
                    for sel in market.get("selections", []):
                        odd_value = sel.get("price")

                        try:
                            if odd_value is not None and float(odd_value) >= min_odd:
                                normalized = normalize_market_entry(
                                    market_raw=market_name,
                                    selection_raw=sel.get("name"),
                                    home_team=home_team,
                                    away_team=away_team,
                                )
                                rows.append(
                                    {
                                        "run_id": run_id,
                                        "collected_at": collected_at,
                                        "source": "betano",
                                        "league": league_name,
                                        "match_datetime": start_time,
                                        "home_team": home_team,
                                        "away_team": away_team,
                                        "match_name": match_name,
                                        "market_raw": market_name,
                                        "selection_raw": sel.get("name"),
                                        "odd": float(odd_value),
                                        "event_url": event_url,
                                        **normalized,
                                    }
                                )
                        except (ValueError, TypeError):
                            continue

        except KeyError:
            logging.error(f"Estrutura de jogo inválida em {url}")

        return rows


def split_match_name(match_name: str) -> Tuple[str, str]:
    if " - " in match_name:
        home_team, away_team = match_name.split(" - ", 1)
        return home_team.strip(), away_team.strip()
    return match_name.strip(), ""


def save_to_csv(data: List[Dict], filename: str | Path):
    if not data:
        return
    with open(filename, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=data[0].keys(), delimiter=";")
        writer.writeheader()
        writer.writerows(data)
    logging.info(f"Arquivo salvo com sucesso: {filename}")


def save_to_json_tree(data: List[Dict], filename: str | Path):
    if not data:
        return

    tree = {}
    for row in data:
        liga = row["league"]
        jogo = f"{row['match_datetime']} | {row['match_name']}"
        mercado = row["market_raw"]
        selecao = row["selection_raw"]
        tree.setdefault(liga, {}).setdefault(jogo, {}).setdefault(mercado, {})[selecao] = row["odd"]

    with open(filename, "w", encoding="utf-8") as arquivo:
        json.dump(tree, arquivo, ensure_ascii=False, separators=(",", ":"))

    logging.info(f"Arquivo JSON salvo com sucesso: {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawler de Odds da Betano")
    grupo_data = parser.add_mutually_exclusive_group()
    grupo_data.add_argument("--d", dest="data", type=str, help="Data específica no formato YYYY-MM-DD (ex: 2026-04-10)")
    grupo_data.add_argument("--a", dest="amanha", action="store_true", help="Força a busca pelos jogos do dia seguinte")
    parser.add_argument("--debug", action="store_true", help="Executa normalmente, mas não salva arquivos no final")
    parser.add_argument("--json", action="store_true", help="Salva também a saída em JSON quando ativado")
    parser.add_argument("--run-id", type=str, help="Identificador único da execução")
    parser.add_argument("--output-dir", type=str, default="data/runs", help="Diretório base para salvar as runs")
    args = parser.parse_args()

    if args.data:
        try:
            datetime.strptime(args.data, "%Y-%m-%d")
            data_alvo = args.data
        except ValueError:
            logging.error("Formato de data inválido na linha de comando! Use YYYY-MM-DD (Ex: 2026-04-10).")
            sys.exit(1)
    elif args.amanha:
        data_alvo = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        data_alvo = datetime.today().strftime("%Y-%m-%d")

    run_id = args.run_id or generate_run_id()
    run_dir = ensure_run_dir(run_id=run_id, target_date=data_alvo, base_output_dir=args.output_dir)

    manifest = build_manifest(
        run_id=run_id,
        target_date=data_alvo,
        run_dir=run_dir,
        odds_snapshot_file=str(run_dir / "odds_snapshot.csv"),
        xg_snapshot_file=str(run_dir / "xg_snapshot.csv"),
        status="odds_initialized",
    )
    save_manifest(run_dir, manifest)

    odd_minima = 1.66
    ligas_alvo = carregar_ligas_betano()

    if not ligas_alvo:
        logging.error("Nenhuma liga ativa com betano_path encontrada em ligas.json.")
        update_manifest(run_dir, status="error", error="Nenhuma liga ativa com betano_path encontrada em ligas.json.")
        sys.exit(1)

    crawler = BetanoExtractor()
    all_odds_data = []

    logging.info(f"=== INICIANDO RASPAGEM PARA A DATA: {data_alvo} | RUN_ID: {run_id} ===")

    for liga in ligas_alvo:
        logging.info(f"-> Buscando jogos para: {liga['nome']}")
        urls = crawler.get_match_urls_by_date(liga["path"], data_alvo)

        if not urls:
            logging.warning(f"Nenhum jogo encontrado para {liga['nome']}. Pulando...")
            continue

        logging.info(f"{len(urls)} jogos encontrados em {liga['nome']}. Extraindo...")

        for match_url in urls:
            match_odds = crawler.extract_all_odds(match_url, min_odd=odd_minima, league_name=liga["nome"], run_id=run_id)
            all_odds_data.extend(match_odds)
            time.sleep(random.uniform(0.5, 1.5))

        time.sleep(random.uniform(2.0, 4.0))

    if all_odds_data:
        odds_snapshot_path = run_dir / "odds_snapshot.csv"
        odds_json_path = run_dir / "odds_snapshot.json"

        if args.debug:
            logging.info("[MODO DEBUG] Nenhum arquivo será salvo.")
        else:
            save_to_csv(all_odds_data, odds_snapshot_path)
            if args.json:
                save_to_json_tree(all_odds_data, odds_json_path)

        if not args.debug and not args.json:
            logging.info("[INFO] JSON não gerado. Use --json para salvar esse formato sob demanda.")

        update_manifest(
            run_dir,
            status="odds_completed",
            odds_rows=len(all_odds_data),
            odds_snapshot_file=str(odds_snapshot_path),
            odds_json_file=str(odds_json_path) if args.json and not args.debug else None,
        )
        logging.info(f"Extração total concluída. {len(all_odds_data)} odds registradas.")
    else:
        update_manifest(run_dir, status="odds_empty", odds_rows=0)
        logging.error("Processamento encerrado. Nenhuma odd atendeu aos critérios nas ligas selecionadas.")
