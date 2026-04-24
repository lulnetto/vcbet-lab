from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

import pandas as pd

IGNORED_MARKET_TERMS = (
    "1º tempo",
    "1° tempo",
    "1o tempo",
    "1 tempo",
    "2º tempo",
    "2° tempo",
    "2o tempo",
    "2 tempo",
    "alternativas",
)


FIRST_HALF_TERMS = ("1º tempo", "1° tempo", "1o tempo", "1 tempo")
SECOND_HALF_TERMS = ("2º tempo", "2° tempo", "2o tempo", "2 tempo")

COMPOSITE_SELECTION_PATTERN = re.compile(r"\s(e|ou)\s|\(|\)", re.IGNORECASE)
LINE_PATTERN = re.compile(r"([-+]?\d+(?:[\.,]\d+)?)")


def slug_text(value: str) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents).strip().casefold()


def parse_numeric_line(text: str) -> float | None:
    match = LINE_PATTERN.search(str(text))
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def compare_team_name(a: str, b: str) -> bool:
    return slug_text(a) == slug_text(b)


def detect_market_scope(market_slug: str) -> str:
    if any(term in market_slug for term in FIRST_HALF_TERMS):
        return "first_half"
    if any(term in market_slug for term in SECOND_HALF_TERMS):
        return "second_half"
    return "full_time"


DEFAULT_NORMALIZED = {
    "market_type": None,
    "market_scope": None,
    "side": None,
    "line": None,
    "target_team_role": None,
    "target_team_name": None,
    "normalized_status": "unknown_market",
}


def normalize_market_entry(
    market_raw: str,
    selection_raw: str,
    home_team: str,
    away_team: str,
) -> Dict[str, Any]:
    market = str(market_raw or "").strip()
    selection = str(selection_raw or "").strip()
    market_slug = slug_text(market)
    selection_slug = slug_text(selection)

    result: Dict[str, Any] = dict(DEFAULT_NORMALIZED)
    result["market_scope"] = detect_market_scope(market_slug)

    if not market or not selection:
        result["normalized_status"] = "parse_error"
        return result

    if result["market_scope"] != "full_time":
        result["normalized_status"] = "ignored_market"
        return result

    if any(term in market_slug for term in IGNORED_MARKET_TERMS):
        result["normalized_status"] = "ignored_market"
        return result

    if COMPOSITE_SELECTION_PATTERN.search(selection):
        result["normalized_status"] = "ignored_market"
        return result

    if "ambas equipes marcam" in market_slug:
        result.update(
            {
                "market_type": "btts",
                "target_team_role": "geral",
                "target_team_name": "geral",
            }
        )
        if selection_slug == "sim":
            result.update({"side": "yes", "line": None, "normalized_status": "ok"})
            return result
        if selection_slug in {"nao", "não"}:
            result.update({"side": "no", "line": None, "normalized_status": "ok"})
            return result
        result["normalized_status"] = "unknown_selection"
        return result

    if "handicap asiatico" in market_slug:
        line = parse_numeric_line(selection)
        if line is None:
            result["normalized_status"] = "unknown_selection"
            return result

        match = re.match(r"^(.*?)\s+[-+]\d+(?:[\.,]\d+)?$", selection)
        if not match:
            result["normalized_status"] = "unknown_selection"
            return result

        team_name = match.group(1).strip()
        if compare_team_name(team_name, home_team):
            target_role = "home"
            side = "home"
            canonical_name = home_team
        elif compare_team_name(team_name, away_team):
            target_role = "away"
            side = "away"
            canonical_name = away_team
        else:
            result["normalized_status"] = "parse_error"
            return result

        result.update(
            {
                "market_type": "asian_handicap",
                "side": side,
                "line": line,
                "target_team_role": target_role,
                "target_team_name": canonical_name,
                "normalized_status": "ok",
            }
        )
        return result

    if market_slug == "total de gols mais/menos":
        line = parse_numeric_line(selection)
        if line is None:
            result["normalized_status"] = "unknown_selection"
            return result
        if selection_slug.startswith("mais de"):
            side = "over"
        elif selection_slug.startswith("menos de"):
            side = "under"
        else:
            result["normalized_status"] = "unknown_selection"
            return result

        result.update(
            {
                "market_type": "total_goals",
                "side": side,
                "line": line,
                "target_team_role": "geral",
                "target_team_name": "geral",
                "normalized_status": "ok",
            }
        )
        return result

    if market_slug == "asiatico (mais/menos) total de gols":
        line = parse_numeric_line(selection)
        if line is None:
            result["normalized_status"] = "unknown_selection"
            return result
        if selection_slug.startswith("mais de"):
            side = "over"
        elif selection_slug.startswith("menos de"):
            side = "under"
        else:
            result["normalized_status"] = "unknown_selection"
            return result

        result.update(
            {
                "market_type": "asian_total",
                "side": side,
                "line": line,
                "target_team_role": "geral",
                "target_team_name": "geral",
                "normalized_status": "ok",
            }
        )
        return result

    if market_slug.endswith(" - total de gols mais/menos"):
        team_name = market.rsplit(" - Total de Gols Mais/Menos", 1)[0].strip()
        line = parse_numeric_line(selection)
        if line is None:
            result["normalized_status"] = "unknown_selection"
            return result

        if selection_slug.startswith("mais de"):
            side = "over"
        elif selection_slug.startswith("menos de"):
            side = "under"
        else:
            result["normalized_status"] = "unknown_selection"
            return result

        if compare_team_name(team_name, home_team):
            target_role = "home"
            canonical_name = home_team
        elif compare_team_name(team_name, away_team):
            target_role = "away"
            canonical_name = away_team
        else:
            result["normalized_status"] = "parse_error"
            return result

        result.update(
            {
                "market_type": "team_total",
                "side": side,
                "line": line,
                "target_team_role": target_role,
                "target_team_name": canonical_name,
                "normalized_status": "ok",
            }
        )
        return result

    result["normalized_status"] = "unknown_market"
    return result


NORMALIZED_COLUMNS = [
    "market_type",
    "market_scope",
    "side",
    "line",
    "target_team_role",
    "target_team_name",
    "normalized_status",
]


def normalize_odds_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    required = {"market_raw", "selection_raw", "home_team", "away_team"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame de odds sem colunas obrigatórias para normalização: {sorted(missing)}")

    normalized_records = [
        normalize_market_entry(
            market_raw=row.get("market_raw"),
            selection_raw=row.get("selection_raw"),
            home_team=row.get("home_team", ""),
            away_team=row.get("away_team", ""),
        )
        for _, row in df.iterrows()
    ]

    normalized_df = pd.DataFrame(normalized_records)
    for col in NORMALIZED_COLUMNS:
        df[col] = normalized_df[col]
    return df
