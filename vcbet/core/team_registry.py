from __future__ import annotations

import csv
import html.parser
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin


DEFAULT_REGISTRY_FILE = Path("configs/team_registry/betano_footystats_aliases.csv")
DEFAULT_REVIEW_FILE = Path("data/team_registry/alias_review_pending.csv")
DEFAULT_SNAPSHOT_FILE = Path("data/team_registry/betano_teams_snapshot.json")

APPROVED_COLUMNS = [
    "league",
    "betano_name",
    "betano_team_id",
    "betano_url",
    "footystats_name",
    "match_status",
    "match_confidence",
    "match_method",
    "approved_at",
    "source",
]

REVIEW_COLUMNS = [
    "league",
    "betano_name",
    "betano_team_id",
    "betano_url",
    "suggested_footystats_name",
    "top_score",
    "review_reason",
    "ambiguous_options",
    "status",
]

GENERIC_TOKENS = {
    "united",
    "city",
    "rangers",
    "nacional",
    "sporting",
    "universidad",
    "atletico",
    "real",
}

COMMON_SUFFIXES = {
    "fc",
    "sc",
    "ac",
    "cf",
    "afc",
    "sv",
    "vfb",
    "vfl",
    "fk",
    "club",
    "de",
    "do",
    "da",
    "the",
}

TRANSLATIONS = {
    "munique": "munich",
    "munchen": "munich",
    "muenchen": "munich",
    "milao": "milan",
    "milan": "milan",
    "koln": "cologne",
    "koln": "cologne",
    "koeln": "cologne",
    "cologne": "cologne",
    "colonia": "cologne",
    "internazionale": "inter",
}


@dataclass(frozen=True)
class BetanoTeam:
    league: str
    name: str
    betano_team_id: str = ""
    betano_url: str = ""


@dataclass(frozen=True)
class RegistryAlias:
    league: str
    betano_name: str
    betano_team_id: str
    betano_url: str
    footystats_name: str
    match_status: str
    match_confidence: str
    match_method: str
    approved_at: str
    source: str


@dataclass(frozen=True)
class ReviewAlias:
    league: str
    betano_name: str
    betano_team_id: str
    betano_url: str
    suggested_footystats_name: str
    top_score: str
    review_reason: str
    ambiguous_options: str
    status: str = "pending_review"


@dataclass(frozen=True)
class MatchCandidate:
    footystats_name: str
    score: float
    normalized_betano: str
    normalized_footystats: str


class BetanoStandingsParser(html.parser.HTMLParser):
    def __init__(self, *, league: str, base_url: str = "https://www.betano.bet.br") -> None:
        super().__init__(convert_charrefs=True)
        self.league = league
        self.base_url = base_url
        self._anchor_href = ""
        self._anchor_chunks: list[str] = []
        self.teams: list[BetanoTeam] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = {key: value or "" for key, value in attrs}
        href = attrs_dict.get("href", "")
        if not href or "/sport/futebol/" not in href:
            return
        self._anchor_href = href
        self._anchor_chunks = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href:
            self._anchor_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._anchor_href:
            return
        name = " ".join(" ".join(self._anchor_chunks).split()).strip()
        href = self._anchor_href
        self._anchor_href = ""
        self._anchor_chunks = []
        if not _looks_like_team_name(name):
            return
        team_id = extract_betano_team_id(href)
        url = urljoin(self.base_url, href)
        team = BetanoTeam(self.league, name, team_id, url)
        if team.name not in {item.name for item in self.teams}:
            self.teams.append(team)


def _looks_like_team_name(value: str) -> bool:
    text = value.strip()
    if len(text) < 2 or len(text) > 80:
        return False
    lowered = text.casefold()
    blocked = {"classificacao", "resultados", "calendario", "ao vivo", "popular", "futebol"}
    if lowered in blocked:
        return False
    if re.search(r"\d", text) and len(text.split()) <= 2:
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", text))


def extract_betano_team_id(url: str) -> str:
    match = re.search(r"/(\d+)/?(?:$|[?#])", url)
    return match.group(1) if match else ""


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_team_name(value: str | None) -> str:
    text = strip_accents(str(value or "").casefold())
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    raw_tokens = [token for token in text.split() if token]
    translated = [TRANSLATIONS.get(token, token) for token in raw_tokens]
    tokens = [token for token in translated if token not in COMMON_SUFFIXES]
    return " ".join(tokens)


def important_tokens(value: str) -> set[str]:
    return {token for token in normalize_team_name(value).split() if token and token not in COMMON_SUFFIXES}


def score_team_match(betano_name: str, footystats_name: str) -> MatchCandidate:
    left = normalize_team_name(betano_name)
    right = normalize_team_name(footystats_name)
    if not left or not right:
        score = 0.0
    elif left == right:
        score = 1.0
    else:
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        intersection = len(left_tokens & right_tokens)
        token_score = intersection / max(len(left_tokens | right_tokens), 1)
        containment_score = intersection / max(min(len(left_tokens), len(right_tokens)), 1)
        sequence_score = SequenceMatcher(None, left, right).ratio()
        score = max(token_score, containment_score, sequence_score)
    return MatchCandidate(footystats_name, round(score, 4), left, right)


def rank_candidates(betano_name: str, footystats_names: Iterable[str]) -> list[MatchCandidate]:
    candidates = [score_team_match(betano_name, name) for name in footystats_names if str(name).strip()]
    return sorted(candidates, key=lambda item: (item.score, item.footystats_name), reverse=True)


def ambiguity_reason(
    betano_name: str,
    ranked: list[MatchCandidate],
    *,
    threshold: float = 0.94,
    margin: float = 0.08,
) -> str | None:
    if not ranked:
        return "no_footystats_candidates"
    top = ranked[0]
    second_score = ranked[1].score if len(ranked) > 1 else 0.0
    reasons: list[str] = []
    if top.score < threshold:
        reasons.append("below_threshold")
    if top.score - second_score < margin:
        reasons.append("low_score_gap")
    tokens = important_tokens(betano_name)
    generic = sorted(tokens & GENERIC_TOKENS)
    if generic:
        reasons.append(f"generic_tokens:{','.join(generic)}")
    shared = [
        item.footystats_name
        for item in ranked[:5]
        if len(tokens & important_tokens(item.footystats_name)) >= max(1, min(2, len(tokens)))
    ]
    if len(shared) > 1 and top.score < 1.0:
        reasons.append("multiple_shared_tokens")
    return "|".join(reasons) if reasons else None


def build_registry_matches(
    betano_teams: Iterable[BetanoTeam],
    footystats_names: Iterable[str],
    *,
    threshold: float = 0.94,
    margin: float = 0.08,
    source: str = "sync_team_aliases",
) -> tuple[list[RegistryAlias], list[ReviewAlias]]:
    approved: list[RegistryAlias] = []
    review: list[ReviewAlias] = []
    approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footy = list(footystats_names)
    for team in betano_teams:
        ranked = rank_candidates(team.name, footy)
        reason = ambiguity_reason(team.name, ranked, threshold=threshold, margin=margin)
        top = ranked[0] if ranked else MatchCandidate("", 0.0, "", "")
        options = " | ".join(f"{item.footystats_name}:{item.score:.4f}" for item in ranked[:5])
        if reason:
            review.append(
                ReviewAlias(
                    league=team.league,
                    betano_name=team.name,
                    betano_team_id=team.betano_team_id,
                    betano_url=team.betano_url,
                    suggested_footystats_name=top.footystats_name,
                    top_score=f"{top.score:.4f}",
                    review_reason=reason,
                    ambiguous_options=options,
                )
            )
            continue
        approved.append(
            RegistryAlias(
                league=team.league,
                betano_name=team.name,
                betano_team_id=team.betano_team_id,
                betano_url=team.betano_url,
                footystats_name=top.footystats_name,
                match_status="MATCH_REGISTRY_APPROVED",
                match_confidence=f"{top.score:.4f}",
                match_method="registry_auto_strict",
                approved_at=approved_at,
                source=source,
            )
        )
    return approved, review


def parse_betano_standings_html(html: str, *, league: str, base_url: str = "https://www.betano.bet.br") -> list[BetanoTeam]:
    parser = BetanoStandingsParser(league=league, base_url=base_url)
    parser.feed(html)
    return parser.teams


def read_registry(path: str | Path = DEFAULT_REGISTRY_FILE) -> list[RegistryAlias]:
    registry_path = Path(path)
    if not registry_path.exists():
        return []
    with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        rows = []
        for row in reader:
            rows.append(RegistryAlias(**{col: str(row.get(col, "") or "") for col in APPROVED_COLUMNS}))
        return rows


def registry_lookup(
    league: str,
    betano_name: str,
    candidates: Iterable[str],
    *,
    registry_file: str | Path = DEFAULT_REGISTRY_FILE,
) -> RegistryAlias | None:
    candidate_names = {normalize_team_name(name): name for name in candidates}
    betano_norm = normalize_team_name(betano_name)
    for row in read_registry(registry_file):
        if row.league != league or row.match_status != "MATCH_REGISTRY_APPROVED":
            continue
        if normalize_team_name(row.betano_name) != betano_norm:
            continue
        canonical = candidate_names.get(normalize_team_name(row.footystats_name))
        if canonical:
            return RegistryAlias(
                league=row.league,
                betano_name=row.betano_name,
                betano_team_id=row.betano_team_id,
                betano_url=row.betano_url,
                footystats_name=canonical,
                match_status=row.match_status,
                match_confidence=row.match_confidence,
                match_method=row.match_method,
                approved_at=row.approved_at,
                source=row.source,
            )
    return None


def write_registry_aliases(rows: list[RegistryAlias], path: str | Path = DEFAULT_REGISTRY_FILE) -> tuple[int, int]:
    registry_path = Path(path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_registry(registry_path)
    by_key = {(row.league, normalize_team_name(row.betano_name)): row for row in existing}
    added = 0
    for row in rows:
        key = (row.league, normalize_team_name(row.betano_name))
        if key in by_key:
            continue
        by_key[key] = row
        added += 1
    output = sorted(by_key.values(), key=lambda item: (item.league, normalize_team_name(item.betano_name)))
    with registry_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=APPROVED_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in output:
            writer.writerow(asdict(row))
    return added, len(output)


def write_review_aliases(rows: list[ReviewAlias], path: str | Path = DEFAULT_REVIEW_FILE) -> int:
    review_path = Path(path)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[tuple[str, str], ReviewAlias] = {}
    if review_path.exists():
        with review_path.open("r", newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                item = ReviewAlias(**{col: str(row.get(col, "") or "") for col in REVIEW_COLUMNS})
                existing[(item.league, normalize_team_name(item.betano_name))] = item
    for row in rows:
        existing[(row.league, normalize_team_name(row.betano_name))] = row
    with review_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in sorted(existing.values(), key=lambda item: (item.league, normalize_team_name(item.betano_name))):
            writer.writerow(asdict(row))
    return len(rows)
