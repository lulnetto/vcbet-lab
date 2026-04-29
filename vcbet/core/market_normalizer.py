from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

import pandas as pd

IGNORED_MARKET_TERMS = (
    "alternativas",
)


FIRST_HALF_TERMS = (
    "1 tempo",
    "1o tempo",
    "1º tempo",
    "1° tempo",
)
SECOND_HALF_TERMS = (
    "2 tempo",
    "2o tempo",
    "2º tempo",
    "2° tempo",
    "segundo tempo",
)
UNSUPPORTED_SCOPE_TERMS = (
    "primeiro tempo",
    "1a parte",
    "1 parte",
    "2a parte",
    "2 parte",
    "intervalo",
)

COMPOSITE_SELECTION_PATTERN = re.compile(r"\s(e|ou)\s|\(|\)", re.IGNORECASE)
LINE_PATTERN = re.compile(r"([-+]?\d+(?:[\.,]\d+)?)")
LINE_SUFFIX_PATTERN = re.compile(r"^(?P<label>.*?)\s+(?P<line>[-+]?\d+(?:[\.,]\d+)?)\s*$")

SUPPORTED_MARKET_TYPE_IDS = {
    13: "total_goals",
    15: "btts",
    84: "home_team_total_ou",
    85: "away_team_total_ou",
    185: "asian_handicap",
    189: "asian_total",
    2818: "total_goals",
    104: "total_goals_alt",
    503: "total_goals_alt",
}


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


def parse_numeric_line_suffix(text: str) -> tuple[str, float] | None:
    match = LINE_SUFFIX_PATTERN.match(str(text).strip())
    if not match:
        return None
    return match.group("label").strip(), float(match.group("line").replace(",", "."))


def compare_team_name(a: str, b: str) -> bool:
    return slug_text(a) == slug_text(b)


def _scope_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(slug_text(term) for term in terms)


FIRST_HALF_SLUGS = _scope_terms(FIRST_HALF_TERMS)
SECOND_HALF_SLUGS = _scope_terms(SECOND_HALF_TERMS)
UNSUPPORTED_SCOPE_SLUGS = _scope_terms(UNSUPPORTED_SCOPE_TERMS)


def detect_market_scope(market_slug: str) -> str:
    market_slug = slug_text(market_slug)
    if any(term in market_slug for term in FIRST_HALF_SLUGS):
        return "first_half"
    if any(term in market_slug for term in SECOND_HALF_SLUGS):
        return "second_half"
    return "full_time"


def detect_market_scope_status(market_slug: str) -> tuple[str | None, str]:
    market_slug = slug_text(market_slug)
    scope = detect_market_scope(market_slug)
    if scope != "full_time":
        return scope, "ok"
    if any(term in market_slug for term in UNSUPPORTED_SCOPE_SLUGS):
        return None, "unsupported_scope"
    if "tempo" in market_slug or "parte" in market_slug or "periodo" in market_slug:
        return None, "unsupported_scope"
    return scope, "ok"


DEFAULT_NORMALIZED = {
    "market_type": None,
    "market_scope": None,
    "side": None,
    "line": None,
    "target_team_role": None,
    "target_team_name": None,
    "normalized_status": "unknown_market",
}


def normalize_betano_market_contract(
    market: dict,
    selection: dict,
    home_team: str,
    away_team: str,
) -> dict | None:
    """Retorna contrato canônico para um mercado/selection Betano.

    Campos retornados:
      - betano_market_type_id
      - betano_market_family
      - market_type
      - market_scope
      - side
      - line
      - target_team_role
      - target_team_name
      - normalized_status
      - unsupported_reason
    """
    type_id_raw = market.get("typeId")
    try:
        type_id = int(type_id_raw) if type_id_raw is not None else None
    except (TypeError, ValueError):
        type_id = None

    if type_id is None:
        return None

    market_name = str(market.get("name") or "")
    market_type_str = str(market.get("type") or "")
    combined_slug = slug_text(f"{market_name} {market_type_str}")

    scope = detect_market_scope(combined_slug)
    if scope != "full_time":
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
            "market_type": None,
            "market_scope": scope,
            "side": None,
            "line": None,
            "target_team_role": None,
            "target_team_name": None,
            "normalized_status": "unsupported_scope",
            "unsupported_reason": f"scope_{scope}",
        }

    if any(term in combined_slug for term in UNSUPPORTED_SCOPE_SLUGS):
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
            "market_type": None,
            "market_scope": None,
            "side": None,
            "line": None,
            "target_team_role": None,
            "target_team_name": None,
            "normalized_status": "unsupported_scope",
            "unsupported_reason": "unsupported_scope_term",
        }

    if "tempo" in combined_slug or "parte" in combined_slug or "periodo" in combined_slug:
        # Extra safety: any remaining half/part references
        # But be careful: "tempo" could appear in "tempo regulamentar" which is full_time.
        # Only reject if it looks like first/second half.
        if any(term in combined_slug for term in FIRST_HALF_SLUGS + SECOND_HALF_SLUGS):
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": None,
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unsupported_scope",
                "unsupported_reason": "scope_half_period",
            }

    selection_name = str(selection.get("name") or "")
    selection_slug = slug_text(selection_name)

    # --- BTTS ---
    if type_id == 15:
        if selection_slug == "sim":
            side = "yes"
        elif selection_slug in {"nao", "não"}:
            side = "no"
        else:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": "btts",
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "btts_selection_not_yes_no",
            }
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": "btts",
            "market_type": "btts",
            "market_scope": "full_time",
            "side": side,
            "line": None,
            "target_team_role": "geral",
            "target_team_name": "geral",
            "normalized_status": "ok",
            "unsupported_reason": None,
        }

    # --- Total Goals O/U (typeId 13) ---
    if type_id == 13:
        line = selection.get("handicap")
        if line is None:
            line = market.get("handicap")
        if line is None:
            line = parse_numeric_line(selection_name)
        if line is None:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "missing_line",
            }
        if selection_slug.startswith("mais de"):
            side = "over"
        elif selection_slug.startswith("menos de"):
            side = "under"
        else:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "selection_not_over_under",
            }
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
            "market_type": "total_goals",
            "market_scope": "full_time",
            "side": side,
            "line": float(line),
            "target_team_role": "geral",
            "target_team_name": "geral",
            "normalized_status": "ok",
            "unsupported_reason": None,
        }

    # --- Asian Total (typeId 189) ---
    if type_id == 189:
        line = selection.get("handicap")
        if line is None:
            line = market.get("handicap")
        if line is None:
            line = parse_numeric_line(selection_name)
        if line is None:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "missing_line",
            }
        if selection_slug.startswith("mais de"):
            side = "over"
        elif selection_slug.startswith("menos de"):
            side = "under"
        else:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "selection_not_over_under",
            }
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
            "market_type": "asian_total",
            "market_scope": "full_time",
            "side": side,
            "line": float(line),
            "target_team_role": "geral",
            "target_team_name": "geral",
            "normalized_status": "ok",
            "unsupported_reason": None,
        }

    # --- Team Totals (typeId 84, 85) ---
    if type_id in (84, 85):
        line = selection.get("handicap")
        if line is None:
            line = market.get("handicap")
        if line is None:
            line = parse_numeric_line(selection_name)
        if line is None:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "missing_line",
            }
        if selection_slug.startswith("mais de"):
            side = "over"
        elif selection_slug.startswith("menos de"):
            side = "under"
        else:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "selection_not_over_under",
            }
        target_role = "home" if type_id == 84 else "away"
        canonical_name = home_team if target_role == "home" else away_team
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
            "market_type": "team_total",
            "market_scope": "full_time",
            "side": side,
            "line": float(line),
            "target_team_role": target_role,
            "target_team_name": canonical_name,
            "normalized_status": "ok",
            "unsupported_reason": None,
        }

    # --- Asian Handicap (typeId 185) ---
    if type_id == 185:
        parsed = parse_numeric_line_suffix(selection_name)
        if parsed is None:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": "asian_handicap",
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "missing_handicap_line",
            }
        team_name, line = parsed
        if compare_team_name(team_name, home_team):
            target_role = "home"
            canonical_name = home_team
        elif compare_team_name(team_name, away_team):
            target_role = "away"
            canonical_name = away_team
        else:
            return {
                "betano_market_type_id": type_id,
                "betano_market_family": "asian_handicap",
                "market_type": None,
                "market_scope": "full_time",
                "side": None,
                "line": None,
                "target_team_role": None,
                "target_team_name": None,
                "normalized_status": "unparseable_selection",
                "unsupported_reason": "team_not_matched",
            }
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": "asian_handicap",
            "market_type": "asian_handicap",
            "market_scope": "full_time",
            "side": target_role,
            "line": line,
            "target_team_role": target_role,
            "target_team_name": canonical_name,
            "normalized_status": "ok",
            "unsupported_reason": None,
        }

    # --- Range / Exact goals (typeId 2818, 104, 503) ---
    if type_id in (2818, 104, 503):
        return {
            "betano_market_type_id": type_id,
            "betano_market_family": SUPPORTED_MARKET_TYPE_IDS.get(type_id),
            "market_type": None,
            "market_scope": "full_time",
            "side": None,
            "line": None,
            "target_team_role": None,
            "target_team_name": None,
            "normalized_status": "unsupported_market_shape",
            "unsupported_reason": "range_exact_goals_no_parser",
        }

    return None


def _normalize_btts(selection: str, selection_slug: str, result: Dict[str, Any]) -> Dict[str, Any]:
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


def _normalize_asian_handicap(
    selection: str, result: Dict[str, Any], home_team: str, away_team: str
) -> Dict[str, Any]:
    parsed = parse_numeric_line_suffix(selection)
    if parsed is None:
        result["normalized_status"] = "unknown_selection"
        return result

    team_name, line = parsed
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


def _normalize_total_goals(selection: str, selection_slug: str, result: Dict[str, Any]) -> Dict[str, Any]:
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


def _normalize_asian_total(selection: str, selection_slug: str, result: Dict[str, Any]) -> Dict[str, Any]:
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


def _normalize_team_total(
    selection: str,
    selection_slug: str,
    result: Dict[str, Any],
    home_team: str,
    away_team: str,
    target_role: str,
) -> Dict[str, Any]:
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

    canonical_name = home_team if target_role == "home" else away_team

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


def _normalize_by_family(
    family: str,
    selection: str,
    selection_slug: str,
    result: Dict[str, Any],
    home_team: str,
    away_team: str,
) -> Dict[str, Any] | None:
    if family == "btts":
        return _normalize_btts(selection, selection_slug, result)
    if family == "asian_handicap":
        return _normalize_asian_handicap(selection, result, home_team, away_team)
    if family == "asian_total":
        return _normalize_asian_total(selection, selection_slug, result)
    if family in {"asian_total", "total_goals", "total_goals_alt"}:
        return _normalize_total_goals(selection, selection_slug, result)
    if family == "home_team_total_ou":
        return _normalize_team_total(selection, selection_slug, result, home_team, away_team, "home")
    if family == "away_team_total_ou":
        return _normalize_team_total(selection, selection_slug, result, home_team, away_team, "away")
    return None


def normalize_market_entry(
    market_raw: str,
    selection_raw: str,
    home_team: str,
    away_team: str,
    betano_market_type_id: int | None = None,
    betano_market_family: str | None = None,
    contract: dict | None = None,
) -> Dict[str, Any]:
    market = str(market_raw or "").strip()
    selection = str(selection_raw or "").strip()
    market_slug = slug_text(market)
    selection_slug = slug_text(selection)

    result: Dict[str, Any] = dict(DEFAULT_NORMALIZED)
    market_scope, scope_status = detect_market_scope_status(market_slug)
    result["market_scope"] = market_scope

    # If collector already provided a contract, trust it directly
    if contract is not None:
        for key in ("market_type", "market_scope", "side", "line", "target_team_role", "target_team_name", "normalized_status"):
            if key in contract:
                result[key] = contract[key]
        return result

    if not market or not selection:
        result["normalized_status"] = "parse_error"
        return result

    if scope_status != "ok":
        result["normalized_status"] = scope_status
        return result

    if result["market_scope"] != "full_time":
        result["normalized_status"] = "ignored_market"
        return result

    # Preserve total_goals/alternativas when family/type indicates supported O/U
    is_known_total_family = (
        betano_market_family in {"total_goals", "total_goals_alt", "asian_total"}
        or betano_market_type_id in {13, 189, 2818, 104, 503}
    )
    if any(term in market_slug for term in IGNORED_MARKET_TERMS) and not is_known_total_family:
        result["normalized_status"] = "ignored_market"
        return result

    if COMPOSITE_SELECTION_PATTERN.search(selection):
        result["normalized_status"] = "ignored_market"
        return result

    # Priority: betano_market_family when available
    if betano_market_family:
        family_result = _normalize_by_family(
            betano_market_family, selection, selection_slug, result, home_team, away_team
        )
        if family_result is not None:
            return family_result

    # Legacy fallback by market name
    if "ambas equipes marcam" in market_slug:
        return _normalize_btts(selection, selection_slug, result)

    if "handicap asiatico" in market_slug:
        return _normalize_asian_handicap(selection, result, home_team, away_team)

    if market_slug == "total de gols mais/menos":
        return _normalize_total_goals(selection, selection_slug, result)

    if market_slug == "asiatico (mais/menos) total de gols":
        return _normalize_asian_total(selection, selection_slug, result)

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
            betano_market_type_id=row.get("betano_market_type_id"),
            betano_market_family=row.get("betano_market_family"),
        )
        for _, row in df.iterrows()
    ]

    normalized_df = pd.DataFrame(normalized_records)
    for col in NORMALIZED_COLUMNS:
        df[col] = normalized_df[col]
    return df
