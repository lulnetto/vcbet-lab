from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, normalize_sofascore_event_id, update_ledger
from vcbet.core.run_utils import now_str
from vcbet.paths import DEFAULT_OVERRIDES_FILE
RESULTS_REQUIRED_COLUMNS = {"match_name", "home_goals", "away_goals"}
OVERRIDES_REQUIRED_COLUMNS = {"bet_id"}
TERMINAL_STATUS_RAW_TYPES = {"finished", "afterpenalties", "aet"}
NON_FINAL_NOTE_FRAGMENT = "ainda n\u00e3o finalizada"
NON_FINAL_SETTLEMENT_ERROR = "Refusing to settle non-final match result"

TEXT_COLUMNS = [
    "settlement_source",
    "settlement_confidence",
    "settlement_note",
    "sofascore_event_id",
    "settled_at",
    "override_reason",
    "override_updated_at",
    "auto_bet_status",
    "auto_settlement_status",
    "auto_status_raw",
    "manual_bet_status",
    "manual_settlement_status",
    "final_bet_status",
    "final_settlement_status",
    "bet_executed",
    "executed_at",
    "execution_note",
]

NUMERIC_COLUMNS = [
    "auto_home_goals",
    "auto_away_goals",
    "manual_home_goals",
    "manual_away_goals",
    "final_home_goals",
    "final_away_goals",
    "auto_odd_fechamento",
    "manual_odd_fechamento",
    "final_odd_fechamento",
    "odd_executada",
    "stake_units_executada",
    "result_units_model",
    "result_units_real",
]


def _prepare_ledger_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    for column in TEXT_COLUMNS:
        if column in prepared.columns:
            prepared[column] = prepared[column].astype("object")
    for column in NUMERIC_COLUMNS:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    return prepared


def _is_missing(value) -> bool:
    return pd.isna(value) or value == ""


def _clean_status(value) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip().lower()


def _safe_float(value):
    if _is_missing(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    if _is_missing(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _first_present(*values, default=None):
    for value in values:
        if not _is_missing(value):
            return value
    return default


def _status_raw_type(value) -> str:
    text = _clean_status(value)
    return text.split("|", 1)[0].strip() if text else ""


def _is_terminal_status_raw(value) -> bool:
    return _status_raw_type(value) in TERMINAL_STATUS_RAW_TYPES


def _auto_result_is_settleable(row: pd.Series) -> bool:
    return (
        _clean_status(row.get("auto_bet_status")) == "settled"
        and _clean_status(row.get("settlement_confidence")) == "high"
        and _is_terminal_status_raw(row.get("auto_status_raw"))
        and _safe_int(row.get("auto_home_goals")) is not None
        and _safe_int(row.get("auto_away_goals")) is not None
    )


def _result_row_is_settleable(result_row: pd.Series) -> bool:
    return (
        _clean_status(result_row.get("bet_status")) == "settled"
        and _clean_status(result_row.get("settlement_confidence")) == "high"
        and _is_terminal_status_raw(result_row.get("status_raw"))
        and _safe_int(result_row.get("home_goals")) is not None
        and _safe_int(result_row.get("away_goals")) is not None
    )


def validate_no_non_final_settlements(df: pd.DataFrame) -> None:
    if df.empty or "final_bet_status" not in df.columns:
        return

    final_status = df["final_bet_status"].fillna("").astype(str).str.strip().str.lower()
    settled = final_status.eq("settled")
    if not settled.any():
        return

    if "settlement_note" in df.columns:
        note = df["settlement_note"].fillna("").astype(str).str.lower()
        invalid_note = settled & note.str.contains(NON_FINAL_NOTE_FRAGMENT, na=False, regex=False)
    else:
        invalid_note = pd.Series(False, index=df.index)

    if "auto_bet_status" in df.columns:
        auto_status = df["auto_bet_status"].fillna("").astype(str).str.strip().str.lower()
        invalid_auto_status = settled & auto_status.ne("settled")
    else:
        invalid_auto_status = settled

    invalid = invalid_note | invalid_auto_status
    if invalid.any():
        bet_ids = []
        if "bet_id" in df.columns:
            bet_ids = [str(value) for value in df.loc[invalid, "bet_id"].head(5).tolist()]
        suffix = f" | bet_id(s): {', '.join(bet_ids)}" if bet_ids else ""
        raise RuntimeError(f"{NON_FINAL_SETTLEMENT_ERROR}{suffix}")


def settle_total_like(side: str, line: float, value: int) -> str:
    frac = round(abs(line) % 1, 2)
    if frac == 0.5:
        if side == "over":
            return "win" if value > line else "loss"
        return "win" if value < line else "loss"
    if frac == 0.0:
        if value == line:
            return "push"
        if side == "over":
            return "win" if value > line else "loss"
        return "win" if value < line else "loss"
    if frac == 0.25:
        lower = line - 0.25
        upper = line + 0.25
        res = sorted([settle_total_like(side, lower, value), settle_total_like(side, upper, value)])
        if res == ["loss", "push"]:
            return "half_loss"
        if res == ["push", "win"]:
            return "half_win"
        if res == ["win", "win"]:
            return "win"
        if res == ["loss", "loss"]:
            return "loss"
    if frac == 0.75:
        lower = line - 0.25
        upper = line + 0.25
        res = sorted([settle_total_like(side, lower, value), settle_total_like(side, upper, value)])
        if res == ["loss", "push"]:
            return "half_loss"
        if res == ["push", "win"]:
            return "half_win"
        if res == ["win", "win"]:
            return "win"
        if res == ["loss", "loss"]:
            return "loss"
    return "loss"


def settle_asian_handicap(side: str, line: float, home_goals: int, away_goals: int) -> str:
    goal_diff = home_goals - away_goals
    frac = round(abs(line) % 1, 2)

    def settle_component(component_line: float) -> str:
        adjusted = goal_diff + component_line if side == "home" else (-goal_diff) + component_line
        if adjusted > 0:
            return "win"
        if adjusted < 0:
            return "loss"
        return "push"

    if frac in {0.0, 0.5}:
        return settle_component(line)

    if frac in {0.25, 0.75}:
        results = sorted([settle_component(line - 0.25), settle_component(line + 0.25)])
        if results == ["loss", "push"]:
            return "half_loss"
        if results == ["push", "win"]:
            return "half_win"
        if results == ["win", "win"]:
            return "win"
        if results == ["loss", "loss"]:
            return "loss"
        if results == ["push", "push"]:
            return "push"
    return "loss"


def settle_bet(market_type: str, side: str, line: float | None, target_team_role: str, home_goals: int, away_goals: int) -> str:
    if market_type == "btts":
        both = home_goals >= 1 and away_goals >= 1
        if side == "yes":
            return "win" if both else "loss"
        return "loss" if both else "win"

    if market_type in {"total_goals", "asian_total"}:
        return settle_total_like(side, float(line), home_goals + away_goals)

    if market_type == "team_total":
        value = home_goals if target_team_role == "home" else away_goals
        return settle_total_like(side, float(line), value)

    if market_type == "asian_handicap":
        return settle_asian_handicap(side, float(line), home_goals, away_goals)

    return "void"


def compute_result_units(settlement_status: str, odd: float | None, stake_units: float | None) -> float | None:
    if settlement_status in {"pending", "unmatched"}:
        return None
    odd = _safe_float(odd)
    stake = _safe_float(stake_units)
    if stake is None:
        return None
    if settlement_status in {"void", "push"}:
        return 0.0
    if odd is None:
        return None
    if settlement_status == "win":
        return round(stake * (odd - 1.0), 4)
    if settlement_status == "loss":
        return round(-stake, 4)
    if settlement_status == "half_win":
        return round((stake / 2.0) * (odd - 1.0), 4)
    if settlement_status == "half_loss":
        return round(-(stake / 2.0), 4)
    return 0.0


def _slug_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", without_accents.casefold())
    return " ".join(cleaned.split())


def _parse_match_datetime(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return pd.Timestamp.strptime(text, fmt).to_pydatetime()
        except Exception:
            continue
    try:
        return pd.to_datetime(text, errors="coerce").to_pydatetime()
    except Exception:
        return None


def _result_row_score(ledger_row: pd.Series, result_row: pd.Series) -> int:
    ledger_event_id = normalize_sofascore_event_id(ledger_row.get("sofascore_event_id"))
    result_event_id = normalize_sofascore_event_id(
        _first_present(result_row.get("sofascore_event_id"), result_row.get("source_event_id"))
    )
    if ledger_event_id:
        if result_event_id == ledger_event_id:
            return 10**9
        if result_event_id:
            return -10**9

    score = 0

    ledger_league = _slug_text(ledger_row.get("league"))
    result_league = _slug_text(result_row.get("league"))
    if ledger_league and result_league:
        if ledger_league == result_league:
            score += 40
        else:
            return -10**9

    ledger_home = _slug_text(ledger_row.get("home_team"))
    result_home = _slug_text(result_row.get("home_team"))
    if ledger_home == result_home:
        score += 80
    elif ledger_home and result_home and (ledger_home in result_home or result_home in ledger_home):
        score += 40

    ledger_away = _slug_text(ledger_row.get("away_team"))
    result_away = _slug_text(result_row.get("away_team"))
    if ledger_away == result_away:
        score += 80
    elif ledger_away and result_away and (ledger_away in result_away or result_away in ledger_away):
        score += 40

    ledger_match = _slug_text(ledger_row.get("match_name"))
    result_match = _slug_text(result_row.get("match_name"))
    if ledger_match and result_match and ledger_match == result_match:
        score += 20

    ledger_dt = _parse_match_datetime(ledger_row.get("match_datetime"))
    result_dt = _parse_match_datetime(result_row.get("match_datetime"))
    if ledger_dt and result_dt:
        diff_seconds = abs((result_dt - ledger_dt).total_seconds())
        if diff_seconds <= 4 * 3600:
            score += 30
        elif diff_seconds <= 12 * 3600:
            score += 15
        elif diff_seconds <= 24 * 3600:
            score += 5
        elif diff_seconds > 5 * 24 * 3600:
            score -= 40

    return score


def _infer_auto_settlement_status(bet_status: str, explicit_status) -> str:
    if not _is_missing(explicit_status):
        return str(explicit_status)
    normalized = str(bet_status or "").strip().lower()
    if normalized == "unmatched":
        return "unmatched"
    if normalized in {"cancelled", "voided"}:
        return "void"
    return "pending"


def apply_results_file(ledger_df: pd.DataFrame, results_file: str | Path) -> pd.DataFrame:
    results_df = pd.read_csv(results_file, sep=";")
    missing = RESULTS_REQUIRED_COLUMNS - set(results_df.columns)
    if missing:
        raise ValueError(f"Arquivo de resultados sem colunas obrigatórias: {sorted(missing)}")

    updated = _prepare_ledger_dtypes(ledger_df)
    for idx, row in updated.iterrows():
        best_idx = None
        best_score = -10**9
        for res_idx, result_row in results_df.iterrows():
            score = _result_row_score(row, result_row)
            if score > best_score:
                best_score = score
                best_idx = res_idx

        if best_idx is None or best_score < 120:
            continue

        result_row = results_df.loc[best_idx]
        auto_bet_status = result_row.get("bet_status", "open")
        auto_result_settleable = _result_row_is_settleable(result_row)
        auto_settlement_status = _infer_auto_settlement_status(
            str(auto_bet_status),
            result_row.get("settlement_status"),
        )
        if not auto_result_settleable and _clean_status(auto_bet_status) not in {"cancelled", "voided", "unmatched"}:
            auto_settlement_status = "pending"
        updated.at[idx, "auto_home_goals"] = _safe_int(result_row.get("home_goals")) if auto_result_settleable else pd.NA
        updated.at[idx, "auto_away_goals"] = _safe_int(result_row.get("away_goals")) if auto_result_settleable else pd.NA
        updated.at[idx, "auto_bet_status"] = auto_bet_status
        updated.at[idx, "auto_settlement_status"] = auto_settlement_status
        updated.at[idx, "settlement_source"] = result_row.get("settlement_source", "results_file")
        updated.at[idx, "settlement_confidence"] = result_row.get("settlement_confidence", "low")
        updated.at[idx, "auto_status_raw"] = result_row.get("status_raw", pd.NA)

        note_parts = []
        base_note = result_row.get("settlement_note", pd.NA)
        if not _is_missing(base_note):
            note_parts.append(str(base_note))
        status_raw = result_row.get("status_raw", pd.NA)
        if not _is_missing(status_raw):
            note_parts.append(f"status_raw={status_raw}")
        matched_via = result_row.get("matched_via", pd.NA)
        if not _is_missing(matched_via):
            note_parts.append(f"matched_via={matched_via}")
        source_event_id = _first_present(result_row.get("sofascore_event_id"), result_row.get("source_event_id"), default=pd.NA)
        if not _is_missing(source_event_id):
            note_parts.append(f"source_event_id={source_event_id}")
            updated.at[idx, "sofascore_event_id"] = normalize_sofascore_event_id(source_event_id)
        updated.at[idx, "settlement_note"] = " | ".join(note_parts) if note_parts else pd.NA
    return updated


def apply_overrides_file(ledger_df: pd.DataFrame, overrides_file: str | Path) -> pd.DataFrame:
    overrides_df = pd.read_csv(overrides_file, sep=";")
    missing = OVERRIDES_REQUIRED_COLUMNS - set(overrides_df.columns)
    if missing:
        raise ValueError(f"Arquivo de overrides sem colunas obrigatórias: {sorted(missing)}")
    if overrides_df.empty:
        return _prepare_ledger_dtypes(ledger_df)

    overrides_df = overrides_df.copy()
    overrides_df["bet_id"] = overrides_df["bet_id"].astype(str).str.strip()
    overrides_df = overrides_df[overrides_df["bet_id"] != ""]

    overrides_by_bet = overrides_df.drop_duplicates(subset=["bet_id"], keep="last").set_index("bet_id")
    updated = _prepare_ledger_dtypes(ledger_df)
    for idx, row in updated.iterrows():
        bet_id = str(row["bet_id"]).strip()
        if bet_id not in overrides_by_bet.index:
            continue
        override = overrides_by_bet.loc[bet_id]
        for field in [
            "manual_home_goals",
            "manual_away_goals",
            "manual_bet_status",
            "manual_settlement_status",
            "manual_odd_fechamento",
            "odd_executada",
            "stake_units_executada",
            "bet_executed",
            "executed_at",
            "execution_note",
            "override_reason",
        ]:
            if field in override.index and not _is_missing(override[field]):
                updated.at[idx, field] = override[field]
        if any(field in override.index and not _is_missing(override[field]) for field in [
            "manual_home_goals",
            "manual_away_goals",
            "manual_bet_status",
            "manual_settlement_status",
            "manual_odd_fechamento",
            "override_reason",
        ]):
            updated.at[idx, "override_updated_at"] = now_str()
            updated.at[idx, "settlement_source"] = "manual_override"
            updated.at[idx, "settlement_confidence"] = "manual"
    return updated


def resolve_final_fields(ledger_df: pd.DataFrame) -> pd.DataFrame:
    updated = _prepare_ledger_dtypes(ledger_df)
    for idx, row in updated.iterrows():
        auto_result_settleable = _auto_result_is_settleable(row)
        preserve_existing_settled = (
            not auto_result_settleable
            and _clean_status(row.get("final_bet_status")) == "settled"
            and _clean_status(row.get("auto_bet_status")) == "settled"
            and _is_missing(row.get("auto_status_raw"))
        )
        if preserve_existing_settled:
            final_home_goals = row.get("final_home_goals")
            final_away_goals = row.get("final_away_goals")
        elif auto_result_settleable:
            final_home_goals = _first_present(row.get("manual_home_goals"), row.get("auto_home_goals"))
            final_away_goals = _first_present(row.get("manual_away_goals"), row.get("auto_away_goals"))
        else:
            final_home_goals = pd.NA
            final_away_goals = pd.NA
        if preserve_existing_settled:
            final_bet_status = row.get("final_bet_status")
            final_settlement_status = row.get("final_settlement_status")
        else:
            final_bet_status = _first_present(row.get("manual_bet_status"), row.get("auto_bet_status"), row.get("final_bet_status"), default="open")
            final_settlement_status = _first_present(
                row.get("manual_settlement_status"),
                row.get("auto_settlement_status"),
                row.get("final_settlement_status"),
                default="pending",
            )
        final_odd_fechamento = _first_present(row.get("manual_odd_fechamento"), row.get("auto_odd_fechamento"), row.get("final_odd_fechamento"))

        home_goals = _safe_int(final_home_goals)
        away_goals = _safe_int(final_away_goals)
        normalized_final_bet_status = _clean_status(final_bet_status)

        if preserve_existing_settled:
            pass
        elif normalized_final_bet_status in {"voided", "cancelled"}:
            final_settlement_status = "void"
        elif normalized_final_bet_status == "postponed":
            final_settlement_status = "pending"
        elif normalized_final_bet_status == "unmatched":
            final_settlement_status = "unmatched"
        elif auto_result_settleable and home_goals is not None and away_goals is not None:
            final_settlement_status = settle_bet(
                market_type=str(row["market_type"]),
                side=str(row["side"]),
                line=_safe_float(row.get("line")),
                target_team_role=str(row.get("target_team_role", "geral")),
                home_goals=home_goals,
                away_goals=away_goals,
            )
            final_bet_status = "settled"
        else:
            if normalized_final_bet_status == "settled":
                final_bet_status = "open"
            final_settlement_status = "pending"
            home_goals = None
            away_goals = None

        updated.at[idx, "final_home_goals"] = home_goals if home_goals is not None else pd.NA
        updated.at[idx, "final_away_goals"] = away_goals if away_goals is not None else pd.NA
        updated.at[idx, "final_bet_status"] = final_bet_status if not _is_missing(final_bet_status) else "open"
        updated.at[idx, "final_settlement_status"] = final_settlement_status if not _is_missing(final_settlement_status) else "pending"
        updated.at[idx, "final_odd_fechamento"] = final_odd_fechamento if not _is_missing(final_odd_fechamento) else pd.NA

        if str(updated.at[idx, "final_bet_status"]) == "settled" and _is_missing(updated.at[idx, "settled_at"]):
            updated.at[idx, "settled_at"] = now_str()

        updated.at[idx, "result_units_model"] = compute_result_units(
            str(updated.at[idx, "final_settlement_status"]),
            _safe_float(row.get("odd_entrada")),
            _safe_float(row.get("stake_units")),
        )

        executed = str(row.get("bet_executed", "no")).strip().lower() == "yes"
        updated.at[idx, "result_units_real"] = compute_result_units(
            str(updated.at[idx, "final_settlement_status"]),
            _safe_float(row.get("odd_executada")) if executed else None,
            _safe_float(row.get("stake_units_executada")) if executed else 0.0,
        )
    return updated


def settle_ledger(
    ledger_file: str | Path = DEFAULT_LEDGER_FILE,
    results_file: str | Path | None = None,
    overrides_file: str | Path | None = DEFAULT_OVERRIDES_FILE,
) -> tuple[Path, int]:
    def mutate(ledger_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        updated = _prepare_ledger_dtypes(ledger_df)
        validate_no_non_final_settlements(updated)
        if results_file:
            updated = apply_results_file(updated, results_file)
        if overrides_file:
            override_path = Path(overrides_file)
            if override_path.exists() and override_path.stat().st_size > 0:
                updated = apply_overrides_file(updated, override_path)
        updated = resolve_final_fields(updated)
        validate_no_non_final_settlements(updated)
        settled_count = int((updated["final_bet_status"].astype(str) == "settled").sum())
        return updated, settled_count

    return update_ledger(ledger_file, mutate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Liquidação do ledger com resultados automáticos e overrides manuais")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="Caminho do bets_ledger.csv")
    parser.add_argument("--results-file", help="CSV com match_name;home_goals;away_goals e colunas opcionais de status")
    parser.add_argument("--overrides-file", default=str(DEFAULT_OVERRIDES_FILE), help="CSV com overrides manuais por bet_id. Se existir, é aplicado automaticamente.")
    parser.add_argument("--no-overrides", action="store_true", help="Ignora o arquivo padrão de overrides nesta execução")
    args = parser.parse_args()

    ledger_path, settled_count = settle_ledger(
        ledger_file=args.ledger_file,
        results_file=args.results_file,
        overrides_file=None if args.no_overrides else args.overrides_file,
    )
    print(f"Ledger atualizado: {ledger_path}")
    print(f"Apostas liquidadas: {settled_count}")
