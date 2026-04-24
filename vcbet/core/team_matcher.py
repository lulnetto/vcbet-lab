from __future__ import annotations

import csv
import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from thefuzz import fuzz, process

DEFAULT_ALIAS_FILE = Path("alias_times.json")
PULAR_SENTINEL = "__PULAR__"


@dataclass
class TeamMatchResult:
    source_name: str
    matched_name: str | None
    match_status: str
    score: int
    suggestion: str | None


@dataclass
class PendingAliasRow:
    run_id: str
    created_at: str
    league: str
    match_name: str
    side: str
    source_name: str
    suggestion: str | None
    score: int
    match_status: str


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def slug_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


def load_alias_cache(alias_file: str | Path | None = None) -> dict[str, str]:
    path = Path(alias_file) if alias_file else DEFAULT_ALIAS_FILE
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as arquivo:
        raw = json.load(arquivo)

    cache: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            mapped = value.get("mapped_name") or value.get("match") or value.get("target")
            if mapped:
                cache[key] = str(mapped)
        else:
            cache[key] = str(value)
    return cache


def save_alias_cache(cache: dict[str, str], alias_file: str | Path | None = None) -> Path:
    path = Path(alias_file) if alias_file else DEFAULT_ALIAS_FILE
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as arquivo:
        json.dump(cache, arquivo, ensure_ascii=False, indent=2)
    return path


def canonical_candidate_name(mapped_name: str, candidates: Iterable[str]) -> str | None:
    mapped_slug = slug_text(mapped_name)
    for candidate in candidates:
        if slug_text(candidate) == mapped_slug:
            return candidate
    return None


def match_team_name(
    source_name: str,
    candidates: list[str],
    alias_cache: dict[str, str] | None = None,
    *,
    high_threshold: int = 90,
    review_threshold: int = 75,
) -> TeamMatchResult:
    alias_cache = alias_cache or {}

    if not source_name or not candidates:
        return TeamMatchResult(
            source_name=source_name,
            matched_name=None,
            match_status="blocked",
            score=0,
            suggestion=None,
        )

    if source_name in alias_cache:
        cached_value = alias_cache[source_name]
        if cached_value == PULAR_SENTINEL:
            return TeamMatchResult(
                source_name=source_name,
                matched_name=None,
                match_status="blocked",
                score=0,
                suggestion=None,
            )
        canonical_name = canonical_candidate_name(cached_value, candidates)
        if canonical_name:
            return TeamMatchResult(
                source_name=source_name,
                matched_name=canonical_name,
                match_status="manual_approved",
                score=100,
                suggestion=canonical_name,
            )

    exact = canonical_candidate_name(source_name, candidates)
    if exact:
        return TeamMatchResult(
            source_name=source_name,
            matched_name=exact,
            match_status="auto_exact",
            score=100,
            suggestion=exact,
        )

    extracted = process.extractOne(source_name, candidates, scorer=fuzz.token_set_ratio)
    if not extracted:
        return TeamMatchResult(
            source_name=source_name,
            matched_name=None,
            match_status="blocked",
            score=0,
            suggestion=None,
        )

    best_match, score = extracted
    score = int(score)

    if score >= high_threshold:
        return TeamMatchResult(
            source_name=source_name,
            matched_name=best_match,
            match_status="auto_fuzzy_high",
            score=score,
            suggestion=best_match,
        )

    if score >= review_threshold:
        return TeamMatchResult(
            source_name=source_name,
            matched_name=None,
            match_status="pending_review",
            score=score,
            suggestion=best_match,
        )

    return TeamMatchResult(
        source_name=source_name,
        matched_name=None,
        match_status="blocked",
        score=score,
        suggestion=best_match,
    )


PENDING_ALIAS_COLUMNS = [
    "run_id",
    "created_at",
    "league",
    "match_name",
    "side",
    "source_name",
    "suggestion",
    "score",
    "match_status",
]


def write_pending_aliases(rows: list[PendingAliasRow], output_file: str | Path) -> Path:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    unique_rows = []
    seen = set()
    for row in rows:
        key = (row.league, row.source_name, row.side)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    with path.open("w", newline="", encoding="utf-8-sig") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=PENDING_ALIAS_COLUMNS, delimiter=";")
        writer.writeheader()
        for row in unique_rows:
            writer.writerow(asdict(row))
    return path
