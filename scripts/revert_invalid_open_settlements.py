from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from vcbet.paths import DEFAULT_LEDGER_FILE


NON_FINAL_NOTE_FRAGMENT = "ainda n\u00e3o finalizada"
CLEAR_COLUMNS = [
    "final_home_goals",
    "final_away_goals",
    "settled_at",
    "result_units_model",
    "result_units_real",
]


def _clean_text_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series("", index=df.index)
    return df[column].fillna("").astype(str).str.strip().str.lower()


def invalid_open_settlement_mask(df: pd.DataFrame) -> pd.Series:
    final_status = _clean_text_series(df, "final_bet_status")
    auto_status = _clean_text_series(df, "auto_bet_status")
    note = _clean_text_series(df, "settlement_note")

    return final_status.eq("settled") & (
        auto_status.ne("settled")
        | note.str.contains(NON_FINAL_NOTE_FRAGMENT, na=False, regex=False)
    )


def backup_path_for(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.bak")
    if not backup.exists():
        return backup
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.name}.{stamp}.bak")


def revert_invalid_open_settlements(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> tuple[Path, int]:
    path = Path(ledger_file)
    if not path.exists():
        raise FileNotFoundError(f"Ledger not found: {path}")

    df = pd.read_csv(path, sep=";")
    mask = invalid_open_settlement_mask(df)
    count = int(mask.sum())
    if count == 0:
        return path, 0

    backup = backup_path_for(path)
    shutil.copy2(path, backup)

    for column in CLEAR_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
        df.loc[mask, column] = pd.NA

    for column, value in {
        "final_bet_status": "open",
        "final_settlement_status": "pending",
    }.items():
        if column not in df.columns:
            df[column] = pd.NA
        df.loc[mask, column] = value

    df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return backup, count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reverte liquidacoes invalidas feitas com partida ainda aberta."
    )
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE), help="Caminho do bets_ledger.csv")
    parser.add_argument("--dry-run", action="store_true", help="Conta linhas invalidas sem alterar o ledger")
    args = parser.parse_args()

    if args.dry_run:
        path = Path(args.ledger_file)
        if not path.exists():
            raise FileNotFoundError(f"Ledger not found: {path}")
        df = pd.read_csv(path, sep=";")
        count = int(invalid_open_settlement_mask(df).sum())
        print(f"Linhas que seriam revertidas: {count}")
        return

    backup, count = revert_invalid_open_settlements(args.ledger_file)
    if count == 0:
        print("Nenhuma liquidacao invalida encontrada.")
        return
    print(f"Linhas revertidas: {count}")
    print(f"Backup criado: {backup}")


if __name__ == "__main__":
    main()
