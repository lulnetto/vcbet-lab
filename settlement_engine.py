from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ledger_manager import DEFAULT_LEDGER_FILE, load_ledger, save_ledger
from run_utils import now_str


RESULTS_REQUIRED_COLUMNS = {"match_name", "home_goals", "away_goals"}
OVERRIDES_REQUIRED_COLUMNS = {"bet_id"}

TEXT_COLUMNS = [
    "settlement_source",
    "settlement_confidence",
    "settlement_note",
    "settled_at",
    "override_reason",
    "override_updated_at",
    "auto_bet_status",
    "auto_settlement_status",
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
    if settlement_status == "pending":
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


def apply_results_file(ledger_df: pd.DataFrame, results_file: str | Path) -> pd.DataFrame:
    results_df = pd.read_csv(results_file, sep=";")
    missing = RESULTS_REQUIRED_COLUMNS - set(results_df.columns)
    if missing:
        raise ValueError(f"Arquivo de resultados sem colunas obrigatórias: {sorted(missing)}")

    if "match_datetime" in results_df.columns:
        results_df = results_df.sort_values(by=["match_name", "match_datetime"])

    results_by_match = results_df.drop_duplicates(subset=["match_name"], keep="last").set_index("match_name")

    updated = _prepare_ledger_dtypes(ledger_df)
    for idx, row in updated.iterrows():
        match_name = row["match_name"]
        if match_name not in results_by_match.index:
            continue
        result_row = results_by_match.loc[match_name]
        updated.at[idx, "auto_home_goals"] = result_row.get("home_goals")
        updated.at[idx, "auto_away_goals"] = result_row.get("away_goals")
        updated.at[idx, "auto_bet_status"] = result_row.get("bet_status", "settled")
        updated.at[idx, "settlement_source"] = result_row.get("settlement_source", "results_file")
        updated.at[idx, "settlement_confidence"] = result_row.get("settlement_confidence", "auto")
        updated.at[idx, "settlement_note"] = result_row.get("settlement_note", pd.NA)
    return updated


def apply_overrides_file(ledger_df: pd.DataFrame, overrides_file: str | Path) -> pd.DataFrame:
    overrides_df = pd.read_csv(overrides_file, sep=";")
    missing = OVERRIDES_REQUIRED_COLUMNS - set(overrides_df.columns)
    if missing:
        raise ValueError(f"Arquivo de overrides sem colunas obrigatórias: {sorted(missing)}")

    overrides_by_bet = overrides_df.drop_duplicates(subset=["bet_id"], keep="last").set_index("bet_id")
    updated = _prepare_ledger_dtypes(ledger_df)
    for idx, row in updated.iterrows():
        bet_id = row["bet_id"]
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
        final_home_goals = row.get("manual_home_goals") if not _is_missing(row.get("manual_home_goals")) else row.get("auto_home_goals")
        final_away_goals = row.get("manual_away_goals") if not _is_missing(row.get("manual_away_goals")) else row.get("auto_away_goals")
        final_bet_status = row.get("manual_bet_status") if not _is_missing(row.get("manual_bet_status")) else row.get("auto_bet_status", "open")
        final_settlement_status = row.get("manual_settlement_status") if not _is_missing(row.get("manual_settlement_status")) else row.get("auto_settlement_status", "pending")
        final_odd_fechamento = row.get("manual_odd_fechamento") if not _is_missing(row.get("manual_odd_fechamento")) else row.get("auto_odd_fechamento")

        home_goals = _safe_int(final_home_goals)
        away_goals = _safe_int(final_away_goals)

        if final_bet_status in {"voided", "cancelled"}:
            final_settlement_status = "void"
        elif final_bet_status == "postponed":
            final_settlement_status = "pending"
        elif home_goals is not None and away_goals is not None and str(final_bet_status) not in {"open", "error", "postponed"}:
            final_settlement_status = settle_bet(
                market_type=str(row["market_type"]),
                side=str(row["side"]),
                line=_safe_float(row.get("line")),
                target_team_role=str(row.get("target_team_role", "geral")),
                home_goals=home_goals,
                away_goals=away_goals,
            )
            final_bet_status = "settled"
        elif home_goals is not None and away_goals is not None and str(final_bet_status) == "open":
            final_settlement_status = settle_bet(
                market_type=str(row["market_type"]),
                side=str(row["side"]),
                line=_safe_float(row.get("line")),
                target_team_role=str(row.get("target_team_role", "geral")),
                home_goals=home_goals,
                away_goals=away_goals,
            )
            final_bet_status = "settled"

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
    overrides_file: str | Path | None = None,
) -> tuple[Path, int]:
    ledger_df = _prepare_ledger_dtypes(load_ledger(ledger_file))
    if results_file:
        ledger_df = apply_results_file(ledger_df, results_file)
    if overrides_file:
        ledger_df = apply_overrides_file(ledger_df, overrides_file)
    ledger_df = resolve_final_fields(ledger_df)
    path = save_ledger(ledger_df, ledger_file)
    settled_count = int((ledger_df["final_bet_status"].astype(str) == "settled").sum())
    return path, settled_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Liquidação do ledger com resultados automáticos e overrides manuais")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="Caminho do bets_ledger.csv")
    parser.add_argument("--results-file", help="CSV com match_name;home_goals;away_goals e colunas opcionais de status")
    parser.add_argument("--overrides-file", help="CSV com overrides manuais por bet_id")
    args = parser.parse_args()

    ledger_path, settled_count = settle_ledger(
        ledger_file=args.ledger_file,
        results_file=args.results_file,
        overrides_file=args.overrides_file,
    )
    print(f"Ledger atualizado: {ledger_path}")
    print(f"Apostas liquidadas: {settled_count}")
