#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
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
    parse_betano_phase_standings_json,
    parse_betano_standings_html_with_diagnostics,
    write_registry_aliases,
    write_review_aliases,
)

DEFAULT_PHASE_CACHE_FILE = Path("data/team_registry/betano_phase_cache.json")
DEBUG_DIR = Path("data/team_registry/debug")


class PhaseDiscoveryError(RuntimeError):
    def __init__(self, reason: str, debug_artifact: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.debug_artifact = debug_artifact


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def standings_url_for_league(league: str) -> str | None:
    meta = obter_meta_liga(league)
    if not meta or not meta.get("betano_path"):
        return None
    return urljoin("https://www.betano.bet.br", str(meta["betano_path"])) + "?bt=standings"


def phase_standings_url(*, sport_id: str, league_id: str, g_league_ids: str, phase_id: str) -> str:
    return "https://www.betano.bet.br/api/league/phaseStandings/?" + urlencode({
        "sportId": sport_id,
        "leagueId": league_id,
        "gLeagueIds": g_league_ids,
        "phaseId": phase_id,
    })


def league_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_team_name(value)).strip("_") or "league"


def is_relevant_betano_url(url: str) -> bool:
    lowered = url.lower()
    return "betano.bet.br" in lowered and (
        "/api/" in lowered
        or "phase" in lowered
        or "standing" in lowered
        or "league" in lowered
        or "competition" in lowered
    )


def extract_phase_params(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if "/api/league/phaseStandings/" not in parsed.path:
        return {}
    qs = parse_qs(parsed.query)
    return {key: str((qs.get(key) or [""])[0]) for key in ("sportId", "leagueId", "gLeagueIds", "phaseId")}


def phase_candidates_from_text(text: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for url in re.findall(r"https?://[^'\"\\\s<>]+", text or ""):
        params = extract_phase_params(url)
        if params.get("phaseId"):
            candidates.append(params)
    for phase_id in sorted(set(re.findall(r'"phaseId"\s*:\s*"?(\d+)"?|phaseId=(\d+)', text or ""))):
        value = next((item for item in phase_id if item), "")
        if value:
            candidates.append({"sportId": "1", "leagueId": "", "gLeagueIds": "", "phaseId": value})
    unique: list[dict[str, str]] = []
    seen = set()
    for item in candidates:
        key = (item.get("sportId", ""), item.get("leagueId", ""), item.get("gLeagueIds", ""), item.get("phaseId", ""))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def write_debug_artifact(root: Path, league: str, payload: dict[str, object]) -> str:
    path = root / DEBUG_DIR / f"betano_phase_{league_slug(league)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.relative_to(root))


def load_phase_cache(root: Path) -> dict[str, dict[str, object]]:
    path = root / DEFAULT_PHASE_CACHE_FILE
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_phase_cache(root: Path, cache: dict[str, dict[str, object]]) -> None:
    path = root / DEFAULT_PHASE_CACHE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def cache_entry_is_valid(entry: dict[str, object]) -> bool:
    return bool(entry.get("phase_id") and entry.get("league_id") and entry.get("api_url"))


def validate_phase_candidate(params: dict[str, str], league: str, fetcher) -> dict[str, object] | None:
    league_id = params.get("leagueId") or params.get("gLeagueIds") or ""
    phase_id = params.get("phaseId") or ""
    if not league_id or not phase_id:
        return None
    api_url = phase_standings_url(
        sport_id=params.get("sportId") or "1",
        league_id=league_id,
        g_league_ids=params.get("gLeagueIds") or league_id,
        phase_id=phase_id,
    )
    payload = fetcher(api_url)
    parsed = parse_betano_phase_standings_json(payload, league=league, source_url=api_url)
    if not parsed.teams or parsed.phase_id != phase_id:
        return None
    return {
        "league": league,
        "league_id": league_id,
        "sport_id": params.get("sportId") or "1",
        "g_league_ids": params.get("gLeagueIds") or league_id,
        "phase_id": parsed.phase_id,
        "phase_title": parsed.phase_title,
        "source_url": "",
        "api_url": api_url,
        "team_count": len(parsed.teams),
        "discovered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_mode": "phase_api",
    }


def discover_phase_with_playwright(league: str, standings_url: str, *, root: Path | None = None, debug_network: bool = False) -> dict[str, object]:
    root = root or project_root()
    debug: dict[str, object] = {
        "league": league,
        "opened_url": standings_url,
        "final_url": None,
        "page_title": None,
        "page_status": None,
        "cookie_consent_detected": False,
        "standings_dom_found": None,
        "captured_requests": [],
        "captured_responses": [],
        "api_requests": [],
        "api_responses": [],
        "candidate_params": [],
        "phase_candidates": [],
        "failure_reason": "",
        "playwright_error": None,
    }

    def write_debug(payload: dict[str, object]) -> str:
        payload["api_requests"] = payload.get("captured_requests", [])
        payload["api_responses"] = payload.get("captured_responses", [])
        payload["phase_candidates"] = payload.get("candidate_params", [])
        return write_debug_artifact(root, league, payload)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        debug["failure_reason"] = f"playwright_unavailable: {exc}"
        debug["playwright_error"] = repr(exc)
        raise PhaseDiscoveryError(str(debug["failure_reason"]), write_debug(debug))

    browser = None
    context = None

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                )
                page = context.new_page()
            except Exception as exc:
                debug["failure_reason"] = f"playwright_launch_failed: {exc}"
                debug["playwright_error"] = repr(exc)
                raise PhaseDiscoveryError(str(debug["failure_reason"]), write_debug(debug))

            def request_json(url: str) -> dict:
                response = context.request.get(url, timeout=15000)
                return response.json()

            def remember_candidate(params: dict[str, str]) -> None:
                if not params.get("phaseId"):
                    return
                league_id = params.get("leagueId") or params.get("gLeagueIds") or league_id_from_url(standings_url)
                item = {
                    "sportId": params.get("sportId") or "1",
                    "leagueId": league_id,
                    "gLeagueIds": params.get("gLeagueIds") or league_id,
                    "phaseId": params.get("phaseId") or "",
                }
                key = (item["sportId"], item["leagueId"], item["gLeagueIds"], item["phaseId"])
                existing = {
                    (
                        str(c.get("sportId", "")),
                        str(c.get("leagueId", "")),
                        str(c.get("gLeagueIds", "")),
                        str(c.get("phaseId", "")),
                    )
                    for c in debug["candidate_params"]
                    if isinstance(c, dict)
                }
                if key not in existing:
                    debug["candidate_params"].append(item)

            def on_request(request):
                if is_relevant_betano_url(request.url):
                    row = {"url": request.url, "method": request.method}
                    debug["captured_requests"].append(row)
                    params = extract_phase_params(request.url)
                    remember_candidate(params)

            def on_response(response):
                url = response.url
                if not is_relevant_betano_url(url):
                    return

                response_item: dict[str, object] = {
                    "url": url,
                    "status": response.status,
                }

                try:
                    headers = response.headers or {}
                    content_type = headers.get("content-type", "")
                    response_item["content_type"] = content_type
                    if "json" in content_type.lower() or "/api/" in url:
                        text = response.text()
                        response_item["body_preview"] = text[:1000]
                        for params in phase_candidates_from_text(text):
                            remember_candidate(params)
                except Exception as exc:
                    response_item["body_error"] = repr(exc)

                debug["captured_responses"].append(response_item)

                params = extract_phase_params(url)
                remember_candidate(params)

            page.on("request", on_request)
            page.on("response", on_response)

            try:
                response = page.goto(standings_url, wait_until="domcontentloaded", timeout=30000)
                debug["page_status"] = response.status if response else None
                debug["final_url"] = page.url
                debug["page_title"] = page.title()
            except Exception as exc:
                debug["failure_reason"] = f"page_goto_failed: {exc}"
                debug["playwright_error"] = repr(exc)
                raise PhaseDiscoveryError(str(debug["failure_reason"]), write_debug(debug))

            for text in ("Aceitar", "Aceito", "Concordo", "Accept", "OK"):
                try:
                    page.get_by_text(text, exact=False).first.click(timeout=1200)
                    debug["cookie_consent_detected"] = True
                    break
                except Exception:
                    continue

            try:
                page.get_by_text("Classificação", exact=False).first.click(timeout=2500)
            except Exception:
                pass

            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            page.wait_for_timeout(4000)

            content = page.content()
            debug["standings_dom_found"] = 'data-qa="standings_team_0"' in content

            for params in phase_candidates_from_text(content):
                remember_candidate(params)

            # Tudo que depende de Playwright precisa acontecer antes de sair do `with`.
            for params in list(debug["candidate_params"]):
                if not isinstance(params, dict):
                    continue
                try:
                    result = validate_phase_candidate(params, league, request_json)
                except Exception as exc:
                    debug.setdefault("candidate_errors", []).append({
                        "params": params,
                        "error": repr(exc),
                    })
                    result = None

                if result:
                    result["source_url"] = standings_url
                    if debug_network:
                        result["debug_artifact"] = write_debug({**debug, "discovered": result})
                    return result

            if debug.get("standings_dom_found"):
                parsed = parse_betano_standings_html_with_diagnostics(content, league=league)
                if parsed.teams:
                    entry = {
                        "league": league,
                        "source_url": standings_url,
                        "api_url": "",
                        "phase_id": "",
                        "phase_title": "rendered_dom_fallback",
                        "team_count": len(parsed.teams),
                        "teams": [team.__dict__ for team in parsed.teams],
                        "discovered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source_mode": "rendered_dom",
                    }
                    if debug_network:
                        entry["debug_artifact"] = write_debug({**debug, "discovered": entry})
                    return entry

            debug["failure_reason"] = "no_api_candidates" if not debug["candidate_params"] else "api_invalid_response"
            raise PhaseDiscoveryError(str(debug["failure_reason"]), write_debug(debug))

    except PhaseDiscoveryError:
        raise
    except Exception as exc:
        debug["failure_reason"] = f"playwright_discovery_failed: {exc}"
        debug["playwright_error"] = repr(exc)
        raise PhaseDiscoveryError(str(debug["failure_reason"]), write_debug(debug))
    finally:
        if context is not None:
            try:
                context.close()
            except Exception as exc:
                debug.setdefault("close_errors", []).append(f"context.close: {exc}")
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                debug.setdefault("close_errors", []).append(f"browser.close: {exc}")


def load_betano_teams_from_phase_api(args: argparse.Namespace, league: str, root: Path) -> tuple[list[BetanoTeam], str, dict[str, object]]:
    standings_url = args.url or standings_url_for_league(league)
    if not standings_url:
        return [], "missing_betano_url", {"source_mode": "phase_api", "error": "missing_betano_url"}
    cache = load_phase_cache(root)
    entry = cache.get(league) if not getattr(args, "force_refresh_phase", False) else None
    if not isinstance(entry, dict) or not cache_entry_is_valid(entry):
        entry = discover_phase_with_playwright(league, standings_url, root=root, debug_network=bool(getattr(args, "debug_network", False)))
        if entry.get("source_mode") == "rendered_dom":
            teams = [BetanoTeam(**team) for team in entry.get("teams", []) if isinstance(team, dict)]
            return teams, str(entry.get("source_url") or standings_url), {
                "source_mode": "rendered_dom",
                "found_phase_standings": False,
                "found_standings_rows": bool(teams),
                "phase_id": "",
                "phase_title": str(entry.get("phase_title") or "rendered_dom_fallback"),
                "team_count": len(teams),
                "raw_count": len(teams),
                "duplicate_count": 0,
                "duplicate_entries": [],
                "debug_artifact": str(entry.get("debug_artifact") or ""),
            }
        cache[league] = entry
        if not getattr(args, "dry_run", False):
            save_phase_cache(root, cache)
    api_url = str(entry["api_url"])
    try:
        payload = fetch_json(api_url)
        parsed = parse_betano_phase_standings_json(payload, league=league, source_url=api_url)
        if not parsed.teams:
            raise RuntimeError("phase_standings_empty")
    except Exception:
        entry = discover_phase_with_playwright(league, standings_url, root=root, debug_network=bool(getattr(args, "debug_network", False)))
        if entry.get("source_mode") == "rendered_dom":
            teams = [BetanoTeam(**team) for team in entry.get("teams", []) if isinstance(team, dict)]
            return teams, str(entry.get("source_url") or standings_url), {
                "source_mode": "rendered_dom",
                "found_phase_standings": False,
                "found_standings_rows": bool(teams),
                "phase_id": "",
                "phase_title": str(entry.get("phase_title") or "rendered_dom_fallback"),
                "team_count": len(teams),
                "raw_count": len(teams),
                "duplicate_count": 0,
                "duplicate_entries": [],
                "debug_artifact": str(entry.get("debug_artifact") or ""),
            }
        cache[league] = entry
        if not getattr(args, "dry_run", False):
            save_phase_cache(root, cache)
        api_url = str(entry["api_url"])
        payload = fetch_json(api_url)
        parsed = parse_betano_phase_standings_json(payload, league=league, source_url=api_url)
    return parsed.teams, api_url, {
        "source_mode": "phase_api",
        "found_phase_standings": bool(parsed.teams and parsed.phase_id),
        "phase_id": parsed.phase_id,
        "phase_title": parsed.phase_title,
        "team_count": len(parsed.teams),
        "raw_count": len(parsed.teams),
        "duplicate_count": 0,
        "duplicate_entries": [],
        "cache_used": bool(cache.get(league) == entry),
        "league_id": str(entry.get("league_id", "")),
        "sport_id": str(entry.get("sport_id", "1")),
        "g_league_ids": str(entry.get("g_league_ids", "")),
        "debug_artifact": str(entry.get("debug_artifact") or ""),
    }


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "VCBet team-alias-sync/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "VCBet team-alias-sync/1.0", "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def league_id_from_url(url: str) -> str:
    matches = re.findall(r"/(\d+)/?", url)
    return matches[-1] if matches else ""


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


def load_betano_teams(args: argparse.Namespace, league: str, root: Path | None = None) -> tuple[list[BetanoTeam], str, dict[str, object]]:
    if args.from_html:
        html_path = Path(args.from_html)
        html = html_path.read_text(encoding="utf-8", errors="replace")
        result = parse_betano_standings_html_with_diagnostics(html, league=league)
        return result.teams, str(html_path), {
            "raw_count": result.raw_count,
            "duplicate_count": result.duplicate_count,
            "duplicate_entries": result.duplicate_entries,
            "found_standings_rows": result.found_standings_rows,
            "source_mode": "saved_html",
        }
    try:
        return load_betano_teams_from_phase_api(args, league, root or project_root())
    except Exception as exc:
        artifact = getattr(exc, "debug_artifact", "")
        if not artifact and getattr(args, "debug_network", False):
            artifact = write_debug_artifact(root or project_root(), league, {
                "league": league,
                "failure_reason": str(exc),
                "opened_url": standings_url_for_league(league) or "",
                "captured_requests": [],
                "captured_responses": [],
            })
        return [], "phase_standings_api", {
            "source_mode": "phase_api",
            "found_phase_standings": False,
            "phase_id": "",
            "phase_title": "",
            "raw_count": 0,
            "duplicate_count": 0,
            "duplicate_entries": [],
            "error": str(exc),
            "debug_artifact": artifact,
        }


def coverage_status(betano_teams: list[BetanoTeam], footystats_teams: list[str], parse_diagnostics: dict[str, object]) -> tuple[str, str]:
    if parse_diagnostics.get("source_mode") == "phase_api" and not parse_diagnostics.get("found_phase_standings"):
        return "blocked", "phase_standings_not_found"
    if parse_diagnostics.get("source_mode") != "phase_api" and not parse_diagnostics.get("found_standings_rows"):
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
    betano_teams, source, parse_diagnostics = load_betano_teams(args, league, root)
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
        review_written = write_review_aliases(
            review,
            root / DEFAULT_REVIEW_FILE,
            approved_path=root / DEFAULT_REGISTRY_FILE,
            synced_leagues=[league],
        )
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
    parser.add_argument("--debug-network", action="store_true", help="Captura rede/DOM da Betano e grava artefato de debug")
    parser.add_argument("--force-refresh-phase", action="store_true", help="Redescobre phaseId da API Betano via Playwright")
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


if __name__ == "__main__":
    raise SystemExit(main())
