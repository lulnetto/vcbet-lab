from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, load_ledger, save_ledger
from vcbet.core.market_normalizer import normalize_market_entry, compare_team_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class BetanoClosingOddsCollector:
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

    def fetch_market_rows(self, event_url: str) -> list[dict[str, Any]]:
        url = f"{event_url}?bt=99"
        response = self.session.get(url, timeout=10)
        state = self._extract_hydration_state(response.text)
        event_data = state.get("data", {}).get("event", {})
        if not event_data:
            return []

        match_name = event_data.get("name", "")
        home_team, away_team = split_match_name(match_name)
        rows: list[dict[str, Any]] = []
        for market in event_data.get("markets", []):
            market_raw = market.get("name")
            for sel in market.get("selections", []):
                price = sel.get("price")
                if price is None:
                    continue
                normalized = normalize_market_entry(
                    market_raw=market_raw,
                    selection_raw=sel.get("name"),
                    home_team=home_team,
                    away_team=away_team,
                )
                rows.append(
                    {
                        "market_raw": market_raw,
                        "selection_raw": sel.get("name"),
                        "odd": float(price),
                        **normalized,
                    }
                )
        return rows


def split_match_name(match_name: str) -> tuple[str, str]:
    if " - " in str(match_name):
        home_team, away_team = str(match_name).split(" - ", 1)
        return home_team.strip(), away_team.strip()
    return str(match_name).strip(), ""


def parse_match_datetime(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def line_matches(row_line: Any, market_line: Any) -> bool:
    if pd.isna(row_line) and pd.isna(market_line):
        return True
    if pd.isna(row_line) or pd.isna(market_line):
        return False
    try:
        return abs(float(row_line) - float(market_line)) < 1e-9
    except Exception:
        return False


def is_open_like(value: Any) -> bool:
    return str(value).strip().lower() in {"", "nan", "open", "pending", "<na>"}


def should_consider_row(
    row: pd.Series,
    now: datetime,
    window_minutes: int,
    allow_past_minutes: int,
    all_pending: bool,
) -> bool:
    event_url = row.get("event_url")
    if pd.isna(event_url) or not str(event_url).strip():
        return False

    if pd.notna(row.get("manual_odd_fechamento")):
        return False

    if all_pending:
        return True

    final_status = str(row.get("final_bet_status", "")).strip().lower()
    settlement_status = str(row.get("final_settlement_status", "")).strip().lower()
    if final_status in {"voided", "cancelled", "settled", "postponed"}:
        return False
    if settlement_status in {"win", "loss", "half_win", "half_loss", "push", "void"}:
        return False

    match_dt = parse_match_datetime(row.get("match_datetime"))
    if match_dt is None:
        return False

    lower_bound = now - timedelta(minutes=allow_past_minutes)
    upper_bound = now + timedelta(minutes=window_minutes)
    return lower_bound <= match_dt <= upper_bound


def market_row_matches(ledger_row: pd.Series, market_row: dict[str, Any]) -> bool:
    if market_row.get("normalized_status") != "ok":
        return False

    if str(ledger_row.get("market_type")) != str(market_row.get("market_type")):
        return False
    if str(ledger_row.get("market_scope")) != str(market_row.get("market_scope")):
        return False
    if str(ledger_row.get("side")) != str(market_row.get("side")):
        return False
    if not line_matches(ledger_row.get("line"), market_row.get("line")):
        return False
    if str(ledger_row.get("target_team_role")) != str(market_row.get("target_team_role")):
        return False

    ledger_target = ledger_row.get("target_team_name")
    market_target = market_row.get("target_team_name")
    if pd.notna(ledger_target) and str(ledger_target).strip() not in {"", "geral"}:
        if not compare_team_name(str(ledger_target), str(market_target)):
            return False

    ledger_market_raw = str(ledger_row.get("market_raw") or "").strip()
    market_market_raw = str(market_row.get("market_raw") or "").strip()
    if ledger_market_raw and market_market_raw and ledger_market_raw == market_market_raw:
        return True

    ledger_selection = str(ledger_row.get("selection_raw") or "").strip()
    market_selection = str(market_row.get("selection_raw") or "").strip()
    if ledger_selection and market_selection and ledger_selection == market_selection:
        return True

    return True


def resolve_final_closing_odd(row: pd.Series) -> Any:
    manual = row.get("manual_odd_fechamento")
    if pd.notna(manual):
        return manual
    auto = row.get("auto_odd_fechamento")
    if pd.notna(auto):
        return auto
    return pd.NA


def collect_closing_odds(
    ledger_file: str | Path,
    window_minutes: int = 20,
    allow_past_minutes: int = 10,
    all_pending: bool = False,
    bet_ids: list[str] | None = None,
) -> tuple[Path, int, int, int]:
    ledger_path = Path(ledger_file)
    df = load_ledger(ledger_path)
    collector = BetanoClosingOddsCollector()
    now = datetime.now()

    target_mask = df.apply(
        lambda row: should_consider_row(
            row,
            now=now,
            window_minutes=window_minutes,
            allow_past_minutes=allow_past_minutes,
            all_pending=all_pending,
        ),
        axis=1,
    )
    target_df = df[target_mask].copy()

    if bet_ids:
        bet_id_set = {str(b).strip() for b in bet_ids if str(b).strip()}
        target_df = target_df[target_df["bet_id"].astype(str).isin(bet_id_set)].copy()

    if target_df.empty:
        save_ledger(df, ledger_path)
        return ledger_path, 0, 0, 0

    by_url: dict[str, list[dict[str, Any]]] = {}
    matched = 0
    fetched_urls = 0
    failed_urls = 0

    for idx, row in target_df.iterrows():
        event_url = str(row["event_url"]).strip()
        if event_url not in by_url:
            try:
                by_url[event_url] = collector.fetch_market_rows(event_url)
                fetched_urls += 1
            except Exception as exc:
                logging.warning("Falha ao coletar closing odds em %s: %s", event_url, exc)
                by_url[event_url] = []
                failed_urls += 1

        market_rows = by_url[event_url]
        if not market_rows:
            continue

        current_match = None
        for market_row in market_rows:
            if market_row_matches(row, market_row):
                current_match = market_row
                break

        if current_match is None:
            continue

        df.at[idx, "auto_odd_fechamento"] = float(current_match["odd"])
        df.at[idx, "final_odd_fechamento"] = resolve_final_closing_odd(df.loc[idx])
        matched += 1

    save_ledger(df, ledger_path)
    return ledger_path, matched, fetched_urls, failed_urls


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coletor de closing odd via event_url da Betano")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="Caminho do bets_ledger.csv")
    parser.add_argument("--window-minutes", type=int, default=20, help="Janela futura em minutos para considerar jogos próximos do kickoff")
    parser.add_argument("--allow-past-minutes", type=int, default=10, help="Tolerância em minutos após o kickoff para ainda tentar capturar a odd")
    parser.add_argument("--all-pending", action="store_true", help="Ignora a janela e tenta capturar para todas as picks pendentes com event_url")
    parser.add_argument("--bet-id", action="append", default=[], help="Filtra para um ou mais bet_id específicos")
    args = parser.parse_args()

    ledger_path, matched, fetched_urls, failed_urls = collect_closing_odds(
        ledger_file=args.ledger_file,
        window_minutes=args.window_minutes,
        allow_past_minutes=args.allow_past_minutes,
        all_pending=args.all_pending,
        bet_ids=args.bet_id,
    )
    print(
        f"[OK] Ledger atualizado: {ledger_path} | odds_fechamento_atualizadas={matched} | "
        f"urls_coletadas={fetched_urls} | urls_com_falha={failed_urls}"
    )
