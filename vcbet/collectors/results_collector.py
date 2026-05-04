from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List

import pandas as pd
import requests

from vcbet.core.config_ligas import obter_sofascore_unique_tournament_id
from vcbet.core.ledger_manager import normalize_ledger_schema
from vcbet.paths import CONFIGS_DIR, DEFAULT_RESULTS_FILE, DEFAULT_RESULTS_DEBUG_DIR

DEFAULT_DEBUG_DIR = DEFAULT_RESULTS_DEBUG_DIR
SOFASCORE_BASE = "https://www.sofascore.com/api/v1"
DEFAULT_SOFASCORE_WARMUP_URL = "https://www.sofascore.com/"
DEFAULT_SOFASCORE_ALIASES_FILE = CONFIGS_DIR / "team_registry" / "sofascore_result_aliases.csv"
TERMINAL_STATUS_RAW_TYPES = {"finished", "afterpenalties", "aet"}
SofascoreAliasMap = dict[tuple[str, str], str]


@dataclass
class MatchTarget:
    league: str
    match_name: str
    home_team: str
    away_team: str
    match_datetime: datetime | None


@dataclass
class MatchResult:
    league: str
    match_name: str
    home_team: str
    away_team: str
    home_goals: int | None
    away_goals: int | None
    bet_status: str
    settlement_source: str
    settlement_confidence: str
    settlement_note: str
    source_url: str | None = None
    matched_via: str | None = None
    status_raw: str | None = None
    source_event_id: str | None = None
    match_datetime: str | None = None


@dataclass
class MatchScore:
    total: int
    home_score: int
    away_score: int
    dt_bonus: int
    candidate: MatchResult
    alias_used: bool = False


class SofascoreBrowserClient:
    """Cliente que tenta buscar o JSON do Sofascore a partir de uma sessão real de navegador.

    Ordem de tentativa por request:
      1. fetch() dentro do contexto da página (mesma origem do Sofascore)
      2. context.request.get() compartilhando cookies do BrowserContext

    Requer `playwright` + navegador Chromium instalado via `playwright install chromium`.
    """

    def __init__(
        self,
        *,
        warmup_url: str = DEFAULT_SOFASCORE_WARMUP_URL,
        headless: bool = True,
        timeout_ms: int = 20000,
        warmup_wait_ms: int = 2500,
        debug: bool = False,
    ) -> None:
        self.warmup_url = warmup_url
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.warmup_wait_ms = warmup_wait_ms
        self.debug = debug
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "SofascoreBrowserClient":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright não está instalado. Instale com `pip install playwright` e `playwright install chromium`."
            ) from exc

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        except Exception as exc:
            raise RuntimeError(
                "Chromium do Playwright não está disponível. Rode `playwright install chromium`."
            ) from exc

        self._context = self._browser.new_context(
            locale="pt-BR",
            timezone_id="America/Maceio",
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) "
                "Gecko/20100101 Firefox/149.0"
            ),
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-GPC": "1",
            },
        )
        self._context.set_default_timeout(self.timeout_ms)
        self._page = self._context.new_page()
        self._page.goto(self.warmup_url, wait_until="domcontentloaded")
        try:
            self._page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 8000))
        except Exception:
            pass
        if self.warmup_wait_ms > 0:
            self._page.wait_for_timeout(self.warmup_wait_ms)
        if self.debug:
            print(f"[DEBUG] Browser warmup OK em: {self.warmup_url}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for obj in (self._page, self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

    def _fetch_via_page(self, url: str) -> tuple[int, str, str]:
        assert self._page is not None
        result = self._page.evaluate(
            """async (targetUrl) => {
                const response = await fetch(targetUrl, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        'accept': 'application/json,text/plain,*/*'
                    }
                });
                const text = await response.text();
                return {
                    status: response.status,
                    url: response.url,
                    text,
                };
            }""",
            url,
        )
        return int(result["status"]), str(result["text"]), str(result["url"])

    def _fetch_via_context(self, url: str) -> tuple[int, str, str]:
        assert self._context is not None
        response = self._context.request.get(
            url,
            headers={"Accept": "application/json,text/plain,*/*"},
            fail_on_status_code=False,
            timeout=self.timeout_ms,
        )
        text = response.text()
        return int(response.status), text, str(response.url)

    def fetch_json(self, url: str) -> dict:
        attempts: list[tuple[str, Callable[[str], tuple[int, str, str]]]] = [
            ("page_fetch", self._fetch_via_page),
            ("context_request", self._fetch_via_context),
        ]
        errors: list[str] = []

        for method_name, method in attempts:
            try:
                status, text, final_url = method(url)
                if self.debug:
                    print(f"[DEBUG] browser {method_name}: status={status} | {final_url}")
                if status >= 400:
                    errors.append(f"{method_name}: HTTP {status}")
                    continue
                return json.loads(text)
            except Exception as exc:
                errors.append(f"{method_name}: {exc}")

        raise RuntimeError(
            f"Falha ao obter JSON via sessão browser do Sofascore para {url}. Tentativas: {' | '.join(errors)}"
        )


def slug_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", without_accents.casefold())
    return " ".join(cleaned.split())


def load_sofascore_aliases(path: str | Path = DEFAULT_SOFASCORE_ALIASES_FILE) -> SofascoreAliasMap:
    alias_path = Path(path)
    if not alias_path.exists() or alias_path.stat().st_size == 0:
        return {}

    aliases_df = pd.read_csv(alias_path, sep=";")
    required = {"league", "ledger_name", "sofascore_name"}
    missing = required - set(aliases_df.columns)
    if missing:
        raise ValueError(f"Arquivo de aliases Sofascore sem colunas obrigatórias: {sorted(missing)}")

    aliases: SofascoreAliasMap = {}
    for _, row in aliases_df.iterrows():
        league = slug_text(str(row.get("league", "")).strip())
        ledger_name = slug_text(str(row.get("ledger_name", "")).strip())
        sofascore_name = str(row.get("sofascore_name", "")).strip()
        if league and ledger_name and sofascore_name:
            aliases[(league, ledger_name)] = sofascore_name
    return aliases


def apply_sofascore_alias(
    league: str,
    team_name: str,
    aliases: SofascoreAliasMap | None = None,
) -> tuple[str, bool]:
    if not aliases:
        return team_name, False
    alias = aliases.get((slug_text(league), slug_text(team_name)))
    if not alias:
        return team_name, False
    return alias, slug_text(alias) != slug_text(team_name)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


TEAM_TOKEN_STOPWORDS = {
    "fc", "cf", "sc", "ac", "afc", "ud", "cd", "rc", "ca", "bk", "fk",
    "club", "de", "the", "sad", "sduq", "u19", "u20", "u21", "u23"
}

TEAM_TOKEN_ALIASES = {
    "sevilha": "sevilla",
    "atleti": "atletico",
    "atleti": "atletico",
    "sportingkc": "sporting",
    "nyc": "new york city",
}


def normalize_team_for_match(value: str | None) -> str:
    base = slug_text(value)
    if not base:
        return ""
    base = base.replace("st ", "saint ")
    tokens: list[str] = []
    for token in base.split():
        token = TEAM_TOKEN_ALIASES.get(token, token)
        if token in TEAM_TOKEN_STOPWORDS:
            continue
        tokens.extend(token.split())
    return " ".join(tokens).strip()


def team_similarity_score(left: str | None, right: str | None) -> int:
    a = normalize_team_for_match(left)
    b = normalize_team_for_match(right)
    if not a or not b:
        return 0
    if a == b:
        return 70
    if a in b or b in a:
        return 50

    ratio = SequenceMatcher(None, a, b).ratio()
    if ratio >= 0.90:
        return 65
    if ratio >= 0.80:
        return 50
    if ratio >= 0.68:
        return 35

    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if a_tokens and b_tokens:
        overlap = len(a_tokens & b_tokens)
        if overlap >= 2:
            return 45
        if overlap == 1:
            return 25
    return 0


def datetime_match_bonus(target_dt: datetime | None, cand_dt_value: str | None) -> int:
    cand_dt = parse_datetime(cand_dt_value)
    if target_dt is None or cand_dt is None:
        return 0

    diff = abs(target_dt - cand_dt)
    if diff <= timedelta(hours=12):
        return 40
    if diff <= timedelta(hours=36):
        return 30
    if diff <= timedelta(days=3):
        return 15
    if diff >= timedelta(days=14):
        return -20
    if diff >= timedelta(days=7):
        return -10
    return 0


def status_raw_type(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return text.split("|", 1)[0].strip() if text else ""


def is_terminal_status_raw(value: str | None) -> bool:
    return status_raw_type(value) in TERMINAL_STATUS_RAW_TYPES


def utc_dt_from_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return None


def format_match_datetime(value: Any) -> str | None:
    dt = utc_dt_from_timestamp(value)
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def format_target_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def load_ledger(ledger_file: str | Path) -> pd.DataFrame:
    return normalize_ledger_schema(pd.read_csv(ledger_file, sep=";"))


def infer_open_mask(df: pd.DataFrame) -> pd.Series:
    for col in ("final_bet_status", "bet_status", "settlement_status", "final_settlement_status"):
        if col not in df.columns:
            continue
        series = df[col].astype(str).str.strip().str.lower()
        if col in {"bet_status", "final_bet_status"}:
            return series.isin({"open", "pending", "postponed", "unmatched", "nan", "", "none"})
        return series.isin({"pending", "nan", "", "none"})
    return pd.Series([True] * len(df), index=df.index)


def build_targets(
    df: pd.DataFrame,
    *,
    only_ready: bool,
    grace_minutes: int,
    only_unmatched: bool = False,
    date: str | None = None,
) -> List[MatchTarget]:
    if only_unmatched:
        if "final_bet_status" not in df.columns:
            base = df.iloc[0:0].copy()
        else:
            final_status = df["final_bet_status"].astype(str).str.strip().str.lower()
            base = df.loc[final_status.eq("unmatched")].copy()
    else:
        open_mask = infer_open_mask(df)
        base = df.loc[open_mask].copy()

    if "match_datetime" in base.columns:
        base["__match_dt"] = base["match_datetime"].apply(parse_datetime)
    else:
        base["__match_dt"] = None

    if date:
        requested_date = datetime.strptime(date, "%Y-%m-%d").date()
        base = base[base["__match_dt"].apply(lambda value: value is not None and value.date() == requested_date)]

    if only_ready:
        now = datetime.now()
        ready_cutoff = now - timedelta(minutes=grace_minutes)
        base = base[base["__match_dt"].notna()]
        base = base[base["__match_dt"] <= ready_cutoff]

    dedup_cols = [c for c in ["league", "match_name", "home_team", "away_team"] if c in base.columns]
    unique_rows = base.drop_duplicates(subset=dedup_cols) if dedup_cols else base

    targets: List[MatchTarget] = []
    for _, row in unique_rows.iterrows():
        targets.append(
            MatchTarget(
                league=str(row.get("league", "")).strip(),
                match_name=str(row.get("match_name", "")).strip(),
                home_team=str(row.get("home_team", "")).strip(),
                away_team=str(row.get("away_team", "")).strip(),
                match_datetime=row.get("__match_dt"),
            )
        )
    return targets


def fetch_json(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
        "Accept": "application/json,text/plain,*/*",
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def get_current_season_id(unique_tournament_id: int, fetcher: Callable[[str], dict] = fetch_json) -> int:
    url = f"{SOFASCORE_BASE}/unique-tournament/{unique_tournament_id}/seasons"
    payload = fetcher(url)
    seasons = payload.get("seasons") or []
    if not seasons:
        raise ValueError(f"Nenhuma season encontrada para unique_tournament_id={unique_tournament_id}")

    current = next((season for season in seasons if season.get("year") and season.get("id") and season.get("hasEventPlayerStatistics")), None)
    if current and current.get("id"):
        return int(current["id"])

    explicit_current = next((season for season in seasons if season.get("current") is True and season.get("id")), None)
    if explicit_current and explicit_current.get("id"):
        return int(explicit_current["id"])

    first = seasons[0]
    if "id" not in first:
        raise ValueError(f"Payload de seasons sem id na primeira season: {first}")
    return int(first["id"])


def get_score_value(score_obj: Any) -> int | None:
    if not isinstance(score_obj, dict):
        return None
    for key in ("current", "display", "normaltime", "period1", "extra1", "total"):
        value = score_obj.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def event_status_to_bet_status(event: dict, home_goals: int | None, away_goals: int | None) -> tuple[str, str, str, str]:
    status = event.get("status") or {}
    status_type = str(status.get("type") or "").strip().lower()
    description = str(status.get("description") or "").strip()
    raw = f"{status_type}|{description}" if description else status_type

    if status_type in {"finished", "afterpenalties", "aet"} and home_goals is not None and away_goals is not None:
        return "settled", "high", "placar final coletado automaticamente via Sofascore", raw
    if status_type in {"finished", "afterpenalties", "aet"}:
        return "open", "low", "status final confirmado mas placar não foi coletado", raw
    if status_type in {"postponed"}:
        return "postponed", "medium", "partida adiada", raw
    if status_type in {"cancelled", "interrupted", "abandoned"}:
        return "cancelled", "medium", "partida cancelada/interrompida", raw
    if status_type in {"notstarted", "inprogress"}:
        return "open", "medium", "partida ainda não finalizada", raw
    if home_goals is not None and away_goals is not None:
        return "open", "low", "placar coletado mas status final não confirmado", raw
    return "open", "low", "não foi possível confirmar placar final", raw


def iter_recent_events(
    unique_tournament_id: int,
    season_id: int,
    min_target_dt: datetime | None,
    max_pages: int,
    fetcher: Callable[[str], dict] = fetch_json,
) -> List[dict]:
    events: List[dict] = []
    seen_ids = set()

    min_target_utc = None
    if min_target_dt is not None:
        min_target_utc = min_target_dt.replace(tzinfo=timezone.utc) - timedelta(days=3)

    for page in range(max_pages):
        url = f"{SOFASCORE_BASE}/unique-tournament/{unique_tournament_id}/season/{season_id}/events/last/{page}"
        payload = fetcher(url)
        batch = payload.get("events") or []
        if not batch:
            break

        for event in batch:
            event_id = event.get("id")
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            events.append(event)

        if min_target_utc is not None:
            oldest_batch_dt = None
            for event in batch:
                dt = utc_dt_from_timestamp(event.get("startTimestamp"))
                if dt is None:
                    continue
                if oldest_batch_dt is None or dt < oldest_batch_dt:
                    oldest_batch_dt = dt
            if oldest_batch_dt is not None and oldest_batch_dt < min_target_utc:
                break

    return events


def build_candidate_from_event(league: str, event: dict, source_url: str, settlement_source: str) -> MatchResult | None:
    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}

    home_name = str(home.get("name") or home.get("shortName") or "").strip()
    away_name = str(away.get("name") or away.get("shortName") or "").strip()
    if not home_name or not away_name:
        return None

    home_goals = get_score_value(event.get("homeScore"))
    away_goals = get_score_value(event.get("awayScore"))
    bet_status, confidence, note, raw = event_status_to_bet_status(event, home_goals, away_goals)
    final_home_goals = home_goals if bet_status == "settled" else None
    final_away_goals = away_goals if bet_status == "settled" else None

    return MatchResult(
        league=league,
        match_name=f"{home_name} - {away_name}",
        home_team=home_name,
        away_team=away_name,
        home_goals=final_home_goals,
        away_goals=final_away_goals,
        bet_status=bet_status,
        settlement_source=settlement_source,
        settlement_confidence=confidence,
        settlement_note=note,
        source_url=source_url,
        matched_via=None,
        status_raw=raw or None,
        source_event_id=str(event.get("id")) if event.get("id") is not None else None,
        match_datetime=format_match_datetime(event.get("startTimestamp")),
    )


def rank_candidates_for_target(
    target: MatchTarget,
    candidates: List[MatchResult],
    aliases: SofascoreAliasMap | None = None,
) -> list[MatchScore]:
    target_home, home_alias_used = apply_sofascore_alias(target.league, target.home_team, aliases)
    target_away, away_alias_used = apply_sofascore_alias(target.league, target.away_team, aliases)

    ranking: list[MatchScore] = []
    for cand in candidates:
        home_score = team_similarity_score(target_home, cand.home_team)
        away_score = team_similarity_score(target_away, cand.away_team)
        dt_bonus = datetime_match_bonus(target.match_datetime, cand.match_datetime)
        total_score = home_score + away_score + dt_bonus

        ranking.append(
            MatchScore(
                total=total_score,
                home_score=home_score,
                away_score=away_score,
                dt_bonus=dt_bonus,
                candidate=cand,
                alias_used=home_alias_used or away_alias_used,
            )
        )

    return sorted(ranking, key=lambda item: item.total, reverse=True)


def match_score_is_accepted(score: MatchScore) -> bool:
    has_strong_team_match = score.home_score >= 35 and score.away_score >= 35
    has_very_strong_team_match = score.home_score >= 50 and score.away_score >= 25
    return (score.total >= 100 and has_strong_team_match) or (score.total >= 110 and has_very_strong_team_match)


def match_rejection_reason(score: MatchScore) -> str:
    if score.total < 100:
        return "MATCH_REJECTED_LOW_TOTAL_SCORE"
    return "MATCH_REJECTED_LOW_TEAM_SCORE"


def rejected_match_note(target: MatchTarget, candidates: List[MatchResult], aliases: SofascoreAliasMap | None = None) -> str:
    ranking = rank_candidates_for_target(target, candidates, aliases=aliases)
    if not ranking:
        return "jogo não localizado no Sofascore | reason=NO_PROVIDER_CANDIDATES"
    best = ranking[0]
    cand = best.candidate
    return (
        "jogo não localizado no Sofascore | "
        f"best={cand.home_team} vs {cand.away_team} | "
        f"score={best.total} home={best.home_score} away={best.away_score} dt={best.dt_bonus} | "
        f"reason={match_rejection_reason(best)}"
    )


def match_result_for_target(
    target: MatchTarget,
    candidates: List[MatchResult],
    debug: bool = False,
    aliases: SofascoreAliasMap | None = None,
) -> MatchResult | None:
    ranking = rank_candidates_for_target(target, candidates, aliases=aliases)

    if debug:
        print(f"[DEBUG] Match alvo: {target.home_team} vs {target.away_team}")
        for idx, score in enumerate(ranking[:5], start=1):
            cand = score.candidate
            away_goals_txt = cand.away_goals if cand.away_goals is not None else "NA"
            alias_txt = " alias=sofascore_result_alias" if score.alias_used else ""
            print(
                f"        top{idx}: score={score.total} (home={score.home_score}, away={score.away_score}, dt={score.dt_bonus}) | "
                f"{cand.home_team} vs {cand.away_team} | "
                f"status={cand.status_raw or '-'} | "
                f"placar={cand.home_goals}-{away_goals_txt}{alias_txt}"
            )

    if not ranking:
        return None

    best_score = ranking[0]
    if not match_score_is_accepted(best_score):
        return None

    matched = MatchResult(**best_score.candidate.__dict__)
    matched.league = target.league
    matched.match_name = target.match_name
    prefix = "sofascore_result_alias;" if best_score.alias_used else ""
    matched.matched_via = (
        f"{prefix}team_score={best_score.total};home={best_score.home_score};"
        f"away={best_score.away_score};dt={best_score.dt_bonus}"
    )
    if matched.bet_status == "open" and not is_terminal_status_raw(matched.status_raw):
        matched.settlement_confidence = "high"
        matched.settlement_note = "evento encontrado no Sofascore, mas ainda não finalizado"
    return matched


def save_debug_payload(debug_dir: Path, league: str, name: str, payload: dict) -> Path:
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / f"{slug_text(league).replace(' ', '_')}_{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _collect_results_generic(
    *,
    targets: List[MatchTarget],
    fetcher: Callable[[str], dict],
    settlement_source: str,
    debug: bool = False,
    debug_dir: Path | None = None,
    max_pages: int = 6,
) -> List[MatchResult]:
    by_league: dict[str, List[MatchTarget]] = {}
    for target in targets:
        by_league.setdefault(target.league, []).append(target)

    aliases = load_sofascore_aliases()
    all_results: List[MatchResult] = []

    for league, league_targets in by_league.items():
        tournament_id = obter_sofascore_unique_tournament_id(league)
        if debug:
            print(f"\n[DEBUG] Liga: {league}")
            print(f"[DEBUG] Sofascore unique_tournament_id: {tournament_id if tournament_id is not None else '(ausente no ligas.json)'}")
            for idx, target in enumerate(league_targets, start=1):
                kickoff = target.match_datetime.strftime('%Y-%m-%d %H:%M') if target.match_datetime else 'sem_data'
                print(f"    [T{idx}] {target.home_team} vs {target.away_team} | kickoff={kickoff}")

        if tournament_id is None:
            for target in league_targets:
                all_results.append(
                    MatchResult(
                        league=target.league,
                        match_name=target.match_name,
                        home_team=target.home_team,
                        away_team=target.away_team,
                        home_goals=None,
                        away_goals=None,
                        bet_status="unmatched",
                        settlement_source="config_missing",
                        settlement_confidence="low",
                        settlement_note="liga sem sofascore_unique_tournament_id no ligas.json",
                        match_datetime=format_target_datetime(target.match_datetime),
                    )
                )
            continue

        try:
            season_id = get_current_season_id(tournament_id, fetcher=fetcher)
            source_url = f"{SOFASCORE_BASE}/unique-tournament/{tournament_id}/season/{season_id}/events/last/0"
            min_target_dt = min((t.match_datetime for t in league_targets if t.match_datetime is not None), default=None)
            events = iter_recent_events(
                tournament_id,
                season_id,
                min_target_dt=min_target_dt,
                max_pages=max_pages,
                fetcher=fetcher,
            )

            if debug:
                print(f"[DEBUG] season_id resolvido: {season_id}")
                print(f"[DEBUG] eventos coletados: {len(events)}")
                if debug_dir is not None:
                    path = save_debug_payload(debug_dir, league, f"{settlement_source}_events_preview", {"events": events[:5]})
                    print(f"[DEBUG] Preview JSON salvo em: {path}")

            candidates = [
                c for e in events
                if (c := build_candidate_from_event(league, e, source_url, settlement_source)) is not None
            ]

            if debug:
                print(f"[DEBUG] candidatos válidos: {len(candidates)}")
                for idx, cand in enumerate(candidates[:5], start=1):
                    score = f"{cand.home_goals}-{cand.away_goals}" if cand.home_goals is not None and cand.away_goals is not None else "sem_placar"
                    print(
                        f"    [{idx}] {cand.home_team} vs {cand.away_team} | "
                        f"status={cand.status_raw or '-'} | bet_status={cand.bet_status} | score={score}"
                    )

        except Exception as exc:
            if debug:
                print(f"[DEBUG] Falha ao consultar {settlement_source} para {league}: {exc}")
            for target in league_targets:
                all_results.append(
                    MatchResult(
                        league=target.league,
                        match_name=target.match_name,
                        home_team=target.home_team,
                        away_team=target.away_team,
                        home_goals=None,
                        away_goals=None,
                        bet_status="open",
                        settlement_source=settlement_source,
                        settlement_confidence="low",
                        settlement_note=f"falha ao consultar {settlement_source}: {exc}",
                        match_datetime=format_target_datetime(target.match_datetime),
                    )
                )
            continue

        for target in league_targets:
            matched = match_result_for_target(target, candidates, debug=debug, aliases=aliases)
            if matched:
                all_results.append(matched)
            else:
                if debug:
                    print(f"[DEBUG] Nenhum match aceito para: {target.home_team} vs {target.away_team}")
                all_results.append(
                    MatchResult(
                        league=target.league,
                        match_name=target.match_name,
                        home_team=target.home_team,
                        away_team=target.away_team,
                        home_goals=None,
                        away_goals=None,
                        bet_status="unmatched",
                        settlement_source=settlement_source,
                        settlement_confidence="low",
                        settlement_note=rejected_match_note(target, candidates, aliases=aliases),
                        source_url=source_url,
                        match_datetime=format_target_datetime(target.match_datetime),
                    )
                )

    return all_results


def collect_results_sofascore_api(
    targets: List[MatchTarget],
    debug: bool = False,
    debug_dir: Path | None = None,
    max_pages: int = 6,
) -> List[MatchResult]:
    return _collect_results_generic(
        targets=targets,
        fetcher=fetch_json,
        settlement_source="sofascore_api",
        debug=debug,
        debug_dir=debug_dir,
        max_pages=max_pages,
    )


def collect_results_sofascore_browser(
    targets: List[MatchTarget],
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
    max_pages: int = 6,
    browser_warmup_url: str = DEFAULT_SOFASCORE_WARMUP_URL,
    browser_timeout_ms: int = 20000,
    browser_warmup_wait_ms: int = 2500,
    browser_headed: bool = False,
) -> List[MatchResult]:
    with SofascoreBrowserClient(
        warmup_url=browser_warmup_url,
        headless=not browser_headed,
        timeout_ms=browser_timeout_ms,
        warmup_wait_ms=browser_warmup_wait_ms,
        debug=debug,
    ) as client:
        return _collect_results_generic(
            targets=targets,
            fetcher=client.fetch_json,
            settlement_source="sofascore_browser",
            debug=debug,
            debug_dir=debug_dir,
            max_pages=max_pages,
        )


def _should_try_api_fallback(result: MatchResult) -> bool:
    if result.home_goals is not None or result.away_goals is not None:
        return False
    note = (result.settlement_note or "").lower()
    if result.settlement_source != "sofascore_browser":
        return False
    return (
        "falha ao consultar" in note
        or "playwright" in note
        or "http 403" in note
        or "http 401" in note
        or "http 429" in note
    )


def collect_results_sofascore_auto(
    targets: List[MatchTarget],
    *,
    debug: bool = False,
    debug_dir: Path | None = None,
    max_pages: int = 6,
    browser_warmup_url: str = DEFAULT_SOFASCORE_WARMUP_URL,
    browser_timeout_ms: int = 20000,
    browser_warmup_wait_ms: int = 2500,
    browser_headed: bool = False,
) -> List[MatchResult]:
    browser_results = collect_results_sofascore_browser(
        targets,
        debug=debug,
        debug_dir=debug_dir,
        max_pages=max_pages,
        browser_warmup_url=browser_warmup_url,
        browser_timeout_ms=browser_timeout_ms,
        browser_warmup_wait_ms=browser_warmup_wait_ms,
        browser_headed=browser_headed,
    )

    unresolved_targets: List[MatchTarget] = []
    unresolved_indexes: List[int] = []
    for idx, result in enumerate(browser_results):
        if _should_try_api_fallback(result):
            unresolved_targets.append(targets[idx])
            unresolved_indexes.append(idx)

    if not unresolved_targets:
        return browser_results

    if debug:
        print(f"[DEBUG] Fallback API acionado para {len(unresolved_targets)} alvo(s)")

    api_results = collect_results_sofascore_api(
        unresolved_targets,
        debug=debug,
        debug_dir=debug_dir,
        max_pages=max_pages,
    )

    merged = list(browser_results)
    for result_idx, api_result in zip(unresolved_indexes, api_results):
        merged[result_idx] = api_result
    return merged


def save_results_csv(results: List[MatchResult], output_file: str | Path) -> Path:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "league",
        "match_name",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "bet_status",
        "settlement_source",
        "settlement_confidence",
        "settlement_note",
        "source_url",
        "matched_via",
        "status_raw",
        "source_event_id",
        "match_datetime",
    ]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)

    return path


def summarize(results: List[MatchResult]) -> str:
    total = len(results)
    settled = sum(1 for r in results if r.bet_status == "settled")
    postponed = sum(1 for r in results if r.bet_status == "postponed")
    voided = sum(1 for r in results if r.bet_status == "voided")
    unmatched = sum(1 for r in results if r.bet_status == "unmatched")
    open_rows = sum(1 for r in results if r.bet_status == "open")
    return (
        f"Resultados coletados: {total} | "
        f"settled={settled} | postponed={postponed} | voided={voided} | "
        f"unmatched={unmatched} | open={open_rows}"
    )


def main():
    parser = argparse.ArgumentParser(description="Coletor automático de resultados via Sofascore")
    parser.add_argument("--ledger-file", required=True, help="Caminho do bets_ledger.csv")
    parser.add_argument("--output-file", default=str(DEFAULT_RESULTS_FILE), help="Caminho do CSV de resultados automáticos")
    parser.add_argument("--all-pending", action="store_true", help="Tenta coletar todos os jogos pendentes, mesmo sem respeitar janela")
    parser.add_argument("--grace-minutes", type=int, default=110, help="Só tenta jogos que começaram há pelo menos X minutos")
    parser.add_argument("--debug", action="store_true", help="Exibe logs detalhados por liga e por match")
    parser.add_argument("--debug-dir", default=str(DEFAULT_DEBUG_DIR), help="Diretório para salvar previews JSON quando debug estiver ativo")
    parser.add_argument("--max-pages", type=int, default=6, help="Quantidade máxima de páginas events/last/{page} por liga")
    parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "browser", "api"],
        help="auto tenta browser primeiro e usa API crua como fallback; browser usa sessão Playwright; api usa requests.",
    )
    parser.add_argument("--browser-warmup-url", default=DEFAULT_SOFASCORE_WARMUP_URL, help="URL aberta no navegador antes dos requests do Sofascore")
    parser.add_argument("--browser-timeout-ms", type=int, default=20000, help="Timeout padrão do Playwright em milissegundos")
    parser.add_argument("--browser-warmup-wait-ms", type=int, default=2500, help="Espera extra após abrir a página do Sofascore")
    parser.add_argument("--browser-headed", action="store_true", help="Abre o Chromium visível para depuração")
    args = parser.parse_args()

    df = load_ledger(args.ledger_file)
    targets = build_targets(df, only_ready=not args.all_pending, grace_minutes=args.grace_minutes)
    if not targets:
        print("Nenhum jogo pendente elegível para coleta.")
        return

    debug_dir = Path(args.debug_dir) if args.debug else None

    if args.debug:
        print(f"[DEBUG] Total de alvos elegíveis: {len(targets)}")
        print(f"[DEBUG] Debug dir: {debug_dir}")
        print(f"[DEBUG] max_pages: {args.max_pages}")
        print(f"[DEBUG] source: {args.source}")

    if args.source == "browser":
        results = collect_results_sofascore_browser(
            targets=targets,
            debug=args.debug,
            debug_dir=debug_dir,
            max_pages=args.max_pages,
            browser_warmup_url=args.browser_warmup_url,
            browser_timeout_ms=args.browser_timeout_ms,
            browser_warmup_wait_ms=args.browser_warmup_wait_ms,
            browser_headed=args.browser_headed,
        )
    elif args.source == "api":
        results = collect_results_sofascore_api(
            targets=targets,
            debug=args.debug,
            debug_dir=debug_dir,
            max_pages=args.max_pages,
        )
    else:
        results = collect_results_sofascore_auto(
            targets=targets,
            debug=args.debug,
            debug_dir=debug_dir,
            max_pages=args.max_pages,
            browser_warmup_url=args.browser_warmup_url,
            browser_timeout_ms=args.browser_timeout_ms,
            browser_warmup_wait_ms=args.browser_warmup_wait_ms,
            browser_headed=args.browser_headed,
        )

    output_path = save_results_csv(results, args.output_file)

    print(summarize(results))
    print(f"Arquivo salvo: {output_path}")


if __name__ == "__main__":
    main()
