import argparse
import csv
import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
from curl_cffi import requests

from vcbet.core.config_ligas import carregar_ligas_betano
from vcbet.core.market_normalizer import normalize_betano_market_contract, normalize_market_entry
from vcbet.core.run_utils import build_manifest, ensure_run_dir, generate_run_id, save_manifest, update_manifest
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION, file_md5, snapshot_time_from_dataframe

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BLOCK_INDICATORS = [
    "landingpages.kaizengaming",
    "Access Denied",
    "Forbidden",
    "Just a moment",
]

MAX_EVENT_FAILURE_RATE = 0.25
MIN_RAW_SELECTIONS_PER_EVENT = 10
MIN_SUPPORTED_ROWS_PER_EVENT = 2
MIN_SUPPORTED_MARKET_TYPES_PER_EVENT = 1
MIN_FINAL_ROWS_TOTAL = 1

LEAGUE_FETCH_RETRIES = 3
EVENT_FETCH_RETRIES = 3
RETRY_DELAY_BASE = 1.0

DEFAULT_BETANO_BT = "14"

SUPPORTED_MARKET_TYPE_IDS = {
    13: "asian_total_or_total_ou",
    15: "btts",
    84: "home_team_total_ou",
    85: "away_team_total_ou",
    185: "asian_handicap",
    189: "asian_total",
    2818: "total_goals",
    104: "total_goals_alt",
    503: "total_goals_alt",
}


def extract_initial_state_json(html: str) -> dict:
    markers = ['window["initial_state"]=', 'window["initial_state"]=']
    start_idx = -1
    for marker in markers:
        idx = html.find(marker)
        if idx != -1:
            start_idx = idx + len(marker)
            break
    if start_idx == -1:
        logging.warning("initial_state marker not found in HTML")
        return {}

    brace_idx = html.find("{", start_idx)
    if brace_idx == -1:
        logging.warning("No opening brace found after initial_state marker")
        return {}

    depth = 0
    in_string = False
    escape = False
    i = brace_idx
    length = len(html)
    while i < length:
        ch = html[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_str = html[brace_idx : i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as exc:
                    logging.warning(f"JSON decode error in initial_state extraction: {exc}")
                    return {}
        i += 1

    logging.warning("Unclosed JSON object in initial_state extraction")
    return {}


def is_page_blocked(text: str) -> str | None:
    for indicator in BLOCK_INDICATORS:
        if indicator in text:
            return indicator
    return None


def _iter_selections(market: dict) -> Iterator[Tuple[dict, dict]]:
    for sel in market.get("selections", []):
        yield sel, {}
    table_layout = market.get("tableLayout") or {}
    for row in table_layout.get("rows", []):
        row_meta = {"table_row_name": row.get("name")}
        for group in row.get("groupSelections", []):
            group_meta = {"group_name": group.get("name")}
            for sel in group.get("selections", []):
                yield sel, {**row_meta, **group_meta}


def force_bt_url(url: str, bt: str = DEFAULT_BETANO_BT) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() != "bt"
    ]
    query.append(("bt", str(bt)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def url_has_expected_bt(url: str, bt: str = DEFAULT_BETANO_BT) -> bool:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return query.get("bt") == str(bt)


def build_betano_api_odds_url(match_path: str, base_url: str = "https://www.betano.bet.br", bt: str = DEFAULT_BETANO_BT) -> str:
    if match_path.startswith("http"):
        parts = urlsplit(match_path)
        path = parts.path
    else:
        path = match_path

    path = path.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path

    if "/api/odds/" not in path:
        path = path.replace("/odds/", "/api/odds/", 1)

    url = f"{base_url}{path}"
    return force_bt_url(url, bt)


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

    def _fetch(self, url: str, description: str, max_retries: int = 3) -> Any:
        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(url, timeout=15)
            except Exception as exc:
                logging.warning(f"{description} fetch error (attempt {attempt}/{max_retries}): {exc}")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} fetch failed after {max_retries} attempts: {exc}") from exc
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            if not (200 <= response.status_code < 300):
                logging.warning(f"{description} non-2xx status {response.status_code} (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} non-2xx status {response.status_code}")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            blocked = is_page_blocked(response.text)
            if blocked:
                logging.warning(f"{description} blocked page indicator '{blocked}' (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} blocked page indicator: {blocked}")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            if 'window["initial_state"]' not in response.text:
                logging.warning(f"{description} missing_initial_state (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} missing_initial_state")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            return response

        raise RuntimeError(f"{description} max retries exceeded")

    def _fetch_json(self, url: str, description: str, max_retries: int = 3) -> dict:
        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(url, timeout=15)
            except Exception as exc:
                logging.warning(f"{description} fetch error (attempt {attempt}/{max_retries}): {exc}")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} fetch failed after {max_retries} attempts: {exc}") from exc
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            if not (200 <= response.status_code < 300):
                logging.warning(f"{description} non-2xx status {response.status_code} (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} non-2xx status {response.status_code}")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                blocked = is_page_blocked(response.text)
                if blocked:
                    logging.warning(f"{description} blocked page indicator '{blocked}' (attempt {attempt}/{max_retries})")
                    if attempt == max_retries:
                        raise RuntimeError(f"{description} blocked page indicator: {blocked}")
                    delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    time.sleep(delay)
                    continue
                if attempt == max_retries:
                    raise RuntimeError(f"{description} response is not JSON (content-type={content_type})")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                logging.warning(f"{description} JSON decode error (attempt {attempt}/{max_retries}): {exc}")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} JSON decode error: {exc}")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            if not isinstance(data, dict) or "data" not in data or "event" not in data.get("data", {}):
                logging.warning(f"{description} missing data.event (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    raise RuntimeError(f"{description} missing data.event in JSON response")
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            logging.info(f"Betano API JSON fetched | requested={url} | final={response.url}")
            return data

        raise RuntimeError(f"{description} max retries exceeded")

    def get_match_urls_by_date(self, league_path: str, target_date: str) -> Tuple[List[str], Dict[str, Any]]:
        url = f"{self.base_url}{league_path}"
        try:
            response = self._fetch(url, description=f"league {league_path}", max_retries=LEAGUE_FETCH_RETRIES)
        except Exception as exc:
            logging.error(f"League fetch failed for {league_path}: {exc}")
            return [], {"success": False, "failure_reason": str(exc)}

        state = extract_initial_state_json(response.text)
        if not state:
            logging.error(f"League page missing_initial_state: {league_path}")
            return [], {"success": False, "failure_reason": "missing_initial_state"}

        match_urls = []
        for block in state.get("data", {}).get("blocks", []):
            for event in block.get("events", []):
                start_time_ms = event.get("startTime")
                if not start_time_ms or "url" not in event:
                    continue
                event_date = datetime.fromtimestamp(start_time_ms / 1000).strftime("%Y-%m-%d")
                if event_date == target_date:
                    match_urls.append(event["url"])

        return list(set(match_urls)), {"success": True, "events_found": len(match_urls)}

    def _parse_event_odds(self, state: dict, league_name: str, run_id: str, event_url: str) -> Tuple[List[Dict], Dict[str, Any]]:
        rows: List[Dict] = []
        diag: Dict[str, Any] = {
            "success": False,
            "raw_markets_seen": 0,
            "raw_selections_seen": 0,
            "supported_market_rows_seen": 0,
            "supported_market_rows_with_valid_odd": 0,
            "normalized_ok_rows": 0,
            "normalized_non_ok_rows": 0,
            "collected_supported_rows": 0,
            "skipped_unsupported_type_id": 0,
            "skipped_unparseable_selection": 0,
            "skipped_unsupported_scope": 0,
            "skipped_unsupported_market_shape": 0,
            "markets_seen_by_name": {},
            "markets_seen_by_type_id": {},
            "supported_market_type_ids_seen": [],
            "supported_market_families_seen": [],
            "failure_reason": None,
            "declared_total_markets": 0,
            "market_completeness_ratio": 0.0,
            "missing_supported_market_type_ids": [],
        }
        try:
            event_data = state["data"]["event"]
            match_name = event_data.get("name", "")
            home_team, away_team = split_match_name(match_name)
            start_time = datetime.fromtimestamp(event_data.get("startTime") / 1000).strftime("%Y-%m-%d %H:%M")
            betano_event_id = event_data.get("id")
            betano_league_id = event_data.get("leagueId")
            total_markets_available = event_data.get("marketsCount")
            declared_total_markets = event_data.get("totalMarketsAvailable") or event_data.get("marketsCount") or event_data.get("marketCount") or 0
            markets = event_data.get("markets", [])
            diag["raw_markets_seen"] = len(markets)
            diag["declared_total_markets"] = declared_total_markets
            if declared_total_markets > 0:
                diag["market_completeness_ratio"] = len(markets) / declared_total_markets
            betano_markets_count = len(markets)

            collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            seen_type_ids: set[int] = set()
            seen_families: set[str] = set()

            for market in markets:
                market_name = market.get("name", "")
                diag["markets_seen_by_name"][market_name] = diag["markets_seen_by_name"].get(market_name, 0) + 1

                market_type = market.get("type")
                raw_type_id = market.get("typeId")
                market_id = market.get("id")

                try:
                    market_type_id = int(raw_type_id) if raw_type_id is not None else None
                except (TypeError, ValueError):
                    market_type_id = None

                if market_type_id is not None:
                    diag["markets_seen_by_type_id"][market_type_id] = diag["markets_seen_by_type_id"].get(market_type_id, 0) + 1

                if market_type_id not in SUPPORTED_MARKET_TYPE_IDS:
                    diag["skipped_unsupported_type_id"] += 1
                    continue

                seen_type_ids.add(market_type_id)

                for sel, meta in _iter_selections(market):
                    diag["raw_selections_seen"] += 1
                    diag["supported_market_rows_seen"] += 1

                    odd_value = sel.get("price")
                    try:
                        if odd_value is None:
                            continue
                        odd_float = float(odd_value)
                        if odd_float <= 0:
                            continue
                    except (ValueError, TypeError):
                        continue

                    contract = normalize_betano_market_contract(
                        market=market,
                        selection=sel,
                        home_team=home_team,
                        away_team=away_team,
                    )

                    if contract is None:
                        diag["skipped_unsupported_type_id"] += 1
                        diag["normalized_non_ok_rows"] += 1
                        continue

                    if contract["normalized_status"] != "ok":
                        if contract["normalized_status"] == "unsupported_scope":
                            diag["skipped_unsupported_scope"] += 1
                        elif contract["normalized_status"] == "unparseable_selection":
                            diag["skipped_unparseable_selection"] += 1
                        elif contract["normalized_status"] == "unsupported_market_shape":
                            diag["skipped_unsupported_market_shape"] += 1
                        diag["normalized_non_ok_rows"] += 1
                        continue

                    diag["supported_market_rows_with_valid_odd"] += 1
                    diag["normalized_ok_rows"] += 1
                    diag["collected_supported_rows"] += 1
                    seen_families.add(contract["betano_market_family"])

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
                            "odd": odd_float,
                            "event_url": event_url,
                            "source_event_id": betano_event_id,
                            "betano_event_id": betano_event_id,
                            "betano_league_id": betano_league_id,
                            "betano_market_id": market_id,
                            "betano_market_type": market_type,
                            "betano_market_type_id": market_type_id,
                            "betano_market_unique_id": market.get("uniqueId"),
                            "betano_market_family": contract["betano_market_family"],
                            "betano_selection_id": sel.get("id"),
                            "betano_bet_ref": sel.get("betRef"),
                            "betano_total_markets_available": total_markets_available,
                            "betano_markets_count": betano_markets_count,
                            "betano_fetch_method": "event_api_odds_bt14",
                            "betano_table_row_name": meta.get("table_row_name"),
                            "betano_group_name": meta.get("group_name"),
                            "market_type": contract["market_type"],
                            "market_scope": contract["market_scope"],
                            "side": contract["side"],
                            "line": contract["line"],
                            "target_team_role": contract["target_team_role"],
                            "target_team_name": contract["target_team_name"],
                            "normalized_status": contract["normalized_status"],
                        }
                    )

            diag["supported_market_type_ids_seen"] = sorted(seen_type_ids)
            diag["supported_market_families_seen"] = sorted(seen_families)
            missing = set(SUPPORTED_MARKET_TYPE_IDS.keys()) - seen_type_ids
            diag["missing_supported_market_type_ids"] = sorted(missing)

            if diag["supported_market_rows_with_valid_odd"] < MIN_SUPPORTED_ROWS_PER_EVENT:
                diag["failure_reason"] = "event_missing_supported_markets"
                logging.warning(
                    f"Evento {event_url} sem mercados suportados suficientes: "
                    f"{diag['supported_market_rows_with_valid_odd']} rows com odd válida (min={MIN_SUPPORTED_ROWS_PER_EVENT})"
                )
                return rows, diag

            if len(seen_type_ids) < MIN_SUPPORTED_MARKET_TYPES_PER_EVENT:
                diag["failure_reason"] = "event_missing_supported_market_types"
                logging.warning(
                    f"Evento {event_url} sem typeIds suportados suficientes: "
                    f"{len(seen_type_ids)} tipos (min={MIN_SUPPORTED_MARKET_TYPES_PER_EVENT})"
                )
                return rows, diag

            diag["success"] = True

        except KeyError as exc:
            diag["failure_reason"] = f"invalid_event_structure: {exc}"
            logging.error(f"Estrutura de jogo inválida em {event_url}: {exc}")

        return rows, diag

    def _extract_from_html_fallback(self, match_path: str, league_name: str, run_id: str) -> Tuple[List[Dict], Dict[str, Any]]:
        event_url = f"{self.base_url}{match_path}" if match_path.startswith("/") else match_path
        url = force_bt_url(event_url, DEFAULT_BETANO_BT)
        last_diag: Dict[str, Any] = {
            "success": False,
            "raw_markets_seen": 0,
            "raw_selections_seen": 0,
            "supported_market_rows_seen": 0,
            "supported_market_rows_with_valid_odd": 0,
            "normalized_ok_rows": 0,
            "normalized_non_ok_rows": 0,
            "collected_supported_rows": 0,
            "skipped_unsupported_type_id": 0,
            "skipped_unparseable_selection": 0,
            "skipped_unsupported_scope": 0,
            "skipped_unsupported_market_shape": 0,
            "markets_seen_by_name": {},
            "markets_seen_by_type_id": {},
            "supported_market_type_ids_seen": [],
            "supported_market_families_seen": [],
            "failure_reason": None,
            "declared_total_markets": 0,
            "market_completeness_ratio": 0.0,
            "missing_supported_market_type_ids": [],
        }

        try:
            response = self._fetch(url, description=f"event_html_fallback {url}", max_retries=1)
        except Exception as exc:
            last_diag["failure_reason"] = str(exc)
            logging.error(f"Event HTML fallback failed for {url}: {exc}")
            return [], last_diag

        state = extract_initial_state_json(response.text)
        if not state:
            last_diag["failure_reason"] = "missing_initial_state"
            logging.error(f"Event HTML fallback missing_initial_state: {url}")
            return [], last_diag

        rows, diag = self._parse_event_odds(state, league_name, run_id, url)
        for row in rows:
            row["betano_fetch_method"] = "event_html_initial_state_bt14_fallback"
        return rows, diag

    def extract_all_odds(self, match_path: str, league_name: str, run_id: str) -> Tuple[List[Dict], Dict[str, Any]]:
        event_url = f"{self.base_url}{match_path}" if match_path.startswith("/") else match_path
        api_url = build_betano_api_odds_url(event_url, self.base_url, DEFAULT_BETANO_BT)

        last_diag: Dict[str, Any] = {
            "success": False,
            "raw_markets_seen": 0,
            "raw_selections_seen": 0,
            "supported_market_rows_seen": 0,
            "supported_market_rows_with_valid_odd": 0,
            "normalized_ok_rows": 0,
            "normalized_non_ok_rows": 0,
            "collected_supported_rows": 0,
            "skipped_unsupported_type_id": 0,
            "skipped_unparseable_selection": 0,
            "skipped_unsupported_scope": 0,
            "skipped_unsupported_market_shape": 0,
            "markets_seen_by_name": {},
            "markets_seen_by_type_id": {},
            "supported_market_type_ids_seen": [],
            "supported_market_families_seen": [],
            "failure_reason": None,
            "declared_total_markets": 0,
            "market_completeness_ratio": 0.0,
            "missing_supported_market_type_ids": [],
        }

        for attempt in range(1, EVENT_FETCH_RETRIES + 1):
            try:
                state = self._fetch_json(api_url, description=f"event_api {api_url}", max_retries=1)
            except Exception as exc:
                last_diag["failure_reason"] = str(exc)
                logging.error(f"Event API fetch failed for {api_url} (attempt {attempt}/{EVENT_FETCH_RETRIES}): {exc}")
                if attempt == EVENT_FETCH_RETRIES:
                    logging.warning(f"Falling back to HTML initial_state for {event_url}")
                    return self._extract_from_html_fallback(match_path, league_name, run_id)
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            rows, diag = self._parse_event_odds(state, league_name, run_id, api_url)
            last_diag = diag

            if diag.get("success"):
                return rows, diag

            if diag.get("failure_reason") == "event_missing_supported_markets":
                logging.warning(
                    f"Evento {api_url} sem mercados suportados na tentativa {attempt}/{EVENT_FETCH_RETRIES}; "
                    f"reattempting..."
                )
                if attempt == EVENT_FETCH_RETRIES:
                    return rows, diag
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
                time.sleep(delay)
                continue

            return rows, diag

        return [], last_diag


def split_match_name(match_name: str) -> Tuple[str, str]:
    if " - " in match_name:
        home_team, away_team = match_name.split(" - ", 1)
        return home_team.strip(), away_team.strip()
    return match_name.strip(), ""


def save_to_csv(data: List[Dict], filename: str | Path, fieldnames: List[str] | None = None):
    if not data and not fieldnames:
        return
    fn = fieldnames or (list(data[0].keys()) if data else [])
    if not fn:
        return
    with open(filename, "w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=fn, delimiter=";")
        writer.writeheader()
        if data:
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


def evaluate_collection_health(total_stats: dict, final_rows: int) -> Tuple[bool, List[str], List[str]]:
    failures: List[str] = []
    warnings: List[str] = []

    if total_stats.get("events_found", 0) == 0:
        return False, ["no_events_found"], []

    if total_stats.get("events_success", 0) == 0:
        return False, ["no_events_success"], []

    events_found = total_stats["events_found"]
    events_failed = total_stats["events_failed"]
    failure_rate = events_failed / events_found if events_found else 0.0
    if failure_rate > MAX_EVENT_FAILURE_RATE:
        failures.append(f"event_failure_rate_{failure_rate:.2f}_exceeds_{MAX_EVENT_FAILURE_RATE}")

    events_success = total_stats["events_success"]
    if events_success > 0:
        avg_raw = total_stats["raw_selections_seen"] / events_success
        if avg_raw < MIN_RAW_SELECTIONS_PER_EVENT:
            failures.append(f"avg_raw_selections_{avg_raw:.1f}_below_{MIN_RAW_SELECTIONS_PER_EVENT}")
        avg_supported = total_stats["supported_market_rows_seen"] / events_success
        if avg_supported < MIN_SUPPORTED_ROWS_PER_EVENT:
            failures.append(f"avg_supported_rows_{avg_supported:.1f}_below_{MIN_SUPPORTED_ROWS_PER_EVENT}")

    if total_stats.get("normalized_ok_rows", 0) == 0 and total_stats.get("raw_selections_seen", 0) > 0:
        failures.append("odds_no_supported_markets_after_normalization")

    if final_rows == 0 and total_stats.get("supported_market_rows_seen", 0) > 0:
        warnings.append("no_final_rows_despite_supported_markets")
    elif final_rows < MIN_FINAL_ROWS_TOTAL:
        warnings.append(f"final_rows_{final_rows}_below_{MIN_FINAL_ROWS_TOTAL}")

    return (not failures), failures, warnings


def build_odds_manifest(
    run_id: str,
    target_date: str,
    status: str,
    league_stats: dict,
    total_stats: dict,
    failure_reasons: list,
    warnings: list,
    output_file: str | None,
) -> dict:
    return {
        "run_id": run_id,
        "target_date": target_date,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "fetch_method": "event_api_odds_bt14",
        "supported_market_type_ids": sorted(SUPPORTED_MARKET_TYPE_IDS.keys()),
        "leagues": {
            name: {
                "events_found": diag.get("events_found", 0),
                "events_success": diag.get("events_success", 0),
                "events_failed": diag.get("events_failed", 0),
                "raw_markets_seen": diag.get("raw_markets_seen", 0),
                "raw_selections_seen": diag.get("raw_selections_seen", 0),
                "supported_market_rows_seen": diag.get("supported_market_rows_seen", 0),
                "supported_market_rows_with_valid_odd": diag.get("supported_market_rows_with_valid_odd", 0),
                "normalized_ok_rows": diag.get("normalized_ok_rows", 0),
                "normalized_non_ok_rows": diag.get("normalized_non_ok_rows", 0),
                "collected_supported_rows": diag.get("collected_supported_rows", 0),
                "skipped_unsupported_type_id": diag.get("skipped_unsupported_type_id", 0),
                "skipped_unparseable_selection": diag.get("skipped_unparseable_selection", 0),
                "skipped_unsupported_scope": diag.get("skipped_unsupported_scope", 0),
                "skipped_unsupported_market_shape": diag.get("skipped_unsupported_market_shape", 0),
                "markets_seen_by_name": diag.get("markets_seen_by_name", {}),
                "markets_seen_by_type_id": diag.get("markets_seen_by_type_id", {}),
                "supported_market_type_ids_seen": diag.get("supported_market_type_ids_seen", []),
                "supported_market_families_seen": diag.get("supported_market_families_seen", []),
                "missing_supported_market_type_ids": diag.get("missing_supported_market_type_ids", []),
            }
            for name, diag in league_stats.items()
        },
        "totals": total_stats,
        "failure_reasons": failure_reasons,
        "warnings": warnings,
        "output_file": output_file,
        "temporal_contract_version": TEMPORAL_CONTRACT_VERSION,
    }



def main():
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

        ligas_alvo = carregar_ligas_betano()

        if not ligas_alvo:
            logging.error("Nenhuma liga ativa com betano_path encontrada em ligas.json.")
            update_manifest(run_dir, status="error", error="Nenhuma liga ativa com betano_path encontrada em ligas.json.")
            sys.exit(1)

        crawler = BetanoExtractor()
        all_odds_data: List[Dict] = []
        league_stats: Dict[str, Dict[str, Any]] = {}
        total_stats = {
            "events_found": 0,
            "events_attempted": 0,
            "events_success": 0,
            "events_failed": 0,
            "raw_markets_seen": 0,
            "raw_selections_seen": 0,
            "supported_market_rows_seen": 0,
            "supported_market_rows_with_valid_odd": 0,
            "normalized_ok_rows": 0,
            "normalized_non_ok_rows": 0,
            "collected_supported_rows": 0,
            "skipped_unsupported_type_id": 0,
            "skipped_unparseable_selection": 0,
            "skipped_unsupported_scope": 0,
            "skipped_unsupported_market_shape": 0,
            "markets_seen_by_name": {},
            "markets_seen_by_type_id": {},
        }

        logging.info(f"=== INICIANDO RASPAGEM PARA A DATA: {data_alvo} | RUN_ID: {run_id} ===")

        for liga in ligas_alvo:
            league_name = liga["nome"]
            league_diag: Dict[str, Any] = {
                "events_found": 0,
                "events_success": 0,
                "events_failed": 0,
                "raw_markets_seen": 0,
                "raw_selections_seen": 0,
                "supported_market_rows_seen": 0,
                "supported_market_rows_with_valid_odd": 0,
                "normalized_ok_rows": 0,
                "normalized_non_ok_rows": 0,
                "collected_supported_rows": 0,
                "skipped_unsupported_type_id": 0,
                "skipped_unparseable_selection": 0,
                "skipped_unsupported_scope": 0,
                "skipped_unsupported_market_shape": 0,
                "markets_seen_by_name": {},
                "markets_seen_by_type_id": {},
            }

            logging.info(f"-> Buscando jogos para: {league_name}")
            try:
                urls, fetch_diag = crawler.get_match_urls_by_date(liga["path"], data_alvo)
            except Exception as exc:
                logging.error(f"League fetch failed for {league_name}: {exc}")
                urls = []
                fetch_diag = {"success": False, "failure_reason": str(exc)}

            if not urls:
                logging.warning(f"Nenhum jogo encontrado para {league_name}. Pulando...")
                league_stats[league_name] = league_diag
                continue

            league_diag["events_found"] = len(urls)
            total_stats["events_found"] += len(urls)

            logging.info(f"{len(urls)} jogos encontrados em {league_name}. Extraindo...")

            for match_url in urls:
                total_stats["events_attempted"] += 1
                try:
                    match_odds, event_diag = crawler.extract_all_odds(match_url, league_name=league_name, run_id=run_id)
                except Exception as exc:
                    logging.error(f"Event fetch failed for {match_url}: {exc}")
                    event_diag = {
                        "success": False,
                        "raw_markets_seen": 0,
                        "raw_selections_seen": 0,
                        "supported_market_rows_seen": 0,
                        "supported_market_rows_with_valid_odd": 0,
                        "normalized_ok_rows": 0,
                        "normalized_non_ok_rows": 0,
                        "collected_supported_rows": 0,
                        "skipped_unsupported_type_id": 0,
                        "skipped_unparseable_selection": 0,
                        "skipped_unsupported_scope": 0,
                        "skipped_unsupported_market_shape": 0,
                        "markets_seen_by_name": {},
                        "markets_seen_by_type_id": {},
                        "failure_reason": str(exc),
                    }
                    match_odds = []

                all_odds_data.extend(match_odds)

                if event_diag.get("success"):
                    total_stats["events_success"] += 1
                    league_diag["events_success"] += 1
                else:
                    total_stats["events_failed"] += 1
                    league_diag["events_failed"] += 1

                for key in (
                    "raw_markets_seen",
                    "raw_selections_seen",
                    "supported_market_rows_seen",
                    "supported_market_rows_with_valid_odd",
                    "normalized_ok_rows",
                    "normalized_non_ok_rows",
                    "collected_supported_rows",
                    "skipped_unsupported_type_id",
                    "skipped_unparseable_selection",
                    "skipped_unsupported_scope",
                    "skipped_unsupported_market_shape",
                ):
                    val = event_diag.get(key, 0)
                    total_stats[key] += val
                    league_diag[key] += val

                for name, count in event_diag.get("markets_seen_by_name", {}).items():
                    league_diag["markets_seen_by_name"][name] = league_diag["markets_seen_by_name"].get(name, 0) + count
                    total_stats["markets_seen_by_name"][name] = total_stats["markets_seen_by_name"].get(name, 0) + count

                for tid, count in event_diag.get("markets_seen_by_type_id", {}).items():
                    league_diag["markets_seen_by_type_id"][tid] = league_diag["markets_seen_by_type_id"].get(tid, 0) + count
                    total_stats["markets_seen_by_type_id"][tid] = total_stats["markets_seen_by_type_id"].get(tid, 0) + count

                time.sleep(random.uniform(0.5, 1.5))

            league_stats[league_name] = league_diag
            time.sleep(random.uniform(2.0, 4.0))

        health_ok, health_reasons, health_warnings = evaluate_collection_health(total_stats, len(all_odds_data))

        odds_manifest = build_odds_manifest(
            run_id=run_id,
            target_date=data_alvo,
            status="completed" if health_ok else "failed",
            league_stats=league_stats,
            total_stats=total_stats,
            failure_reasons=health_reasons,
            warnings=health_warnings,
            output_file=str(run_dir / "odds_snapshot.csv") if (health_ok and all_odds_data) else None,
        )
        odds_manifest_path = run_dir / "odds_collection_manifest.json"
        with open(odds_manifest_path, "w", encoding="utf-8") as f:
            json.dump(odds_manifest, f, ensure_ascii=False, indent=2)

        if not health_ok:
            logging.error(f"Odds collection failed health checks: {health_reasons}")
            update_manifest(
                run_dir,
                status="odds_collection_failed",
                odds_rows=0,
                odds_events_found=total_stats["events_found"],
                odds_events_success=total_stats["events_success"],
                odds_events_failed=total_stats["events_failed"],
                odds_raw_selections_seen=total_stats["raw_selections_seen"],
                odds_supported_rows=total_stats["supported_market_rows_seen"],
                odds_normalized_ok_rows=total_stats["normalized_ok_rows"],
                odds_normalized_non_ok_rows=total_stats["normalized_non_ok_rows"],
                odds_collection_status="failed",
                odds_collection_manifest_file=str(odds_manifest_path),
                odds_failure_reasons=health_reasons,
            )
            sys.exit(1)

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
                odds_snapshot_hash=file_md5(odds_snapshot_path) if odds_snapshot_path.exists() else None,
                odds_snapshot_time=snapshot_time_from_dataframe(pd.DataFrame(all_odds_data)),
                temporal_contract_version=TEMPORAL_CONTRACT_VERSION,
                odds_json_file=str(odds_json_path) if args.json and not args.debug else None,
                odds_events_found=total_stats["events_found"],
                odds_events_success=total_stats["events_success"],
                odds_events_failed=total_stats["events_failed"],
                odds_raw_selections_seen=total_stats["raw_selections_seen"],
                odds_supported_rows=total_stats["supported_market_rows_seen"],
                odds_normalized_ok_rows=total_stats["normalized_ok_rows"],
                odds_normalized_non_ok_rows=total_stats["normalized_non_ok_rows"],
                odds_collection_status="completed",
                odds_collection_manifest_file=str(odds_manifest_path),
            )
            logging.info(f"Extração total concluída. {len(all_odds_data)} odds registradas.")
        else:
            update_manifest(
                run_dir,
                status="odds_empty",
                odds_rows=0,
                odds_events_found=total_stats["events_found"],
                odds_events_success=total_stats["events_success"],
                odds_events_failed=total_stats["events_failed"],
                odds_raw_selections_seen=total_stats["raw_selections_seen"],
                odds_supported_rows=total_stats["supported_market_rows_seen"],
                odds_normalized_ok_rows=total_stats["normalized_ok_rows"],
                odds_normalized_non_ok_rows=total_stats["normalized_non_ok_rows"],
                odds_collection_status="empty",
                odds_collection_manifest_file=str(odds_manifest_path),
            )
            logging.error("Processamento encerrado. Nenhuma odd atendeu aos critérios nas ligas selecionadas.")

if __name__ == "__main__":
    main()
