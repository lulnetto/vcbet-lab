from __future__ import annotations

import argparse
from pathlib import Path

from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, deduplicate_ledger_rows, load_ledger, save_ledger


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove entradas duplicadas do bets_ledger usando identidade estável de aposta.")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE))
    parser.add_argument("--backup", action="store_true", default=True, help="gera backup .bak antes de salvar")
    parser.add_argument("--no-backup", dest="backup", action="store_false")
    args = parser.parse_args()

    path = Path(args.ledger_file)
    df = load_ledger(path)
    cleaned, removed = deduplicate_ledger_rows(df)
    if args.backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        backup_path.write_bytes(path.read_bytes())
        print(f"[backup] {backup_path}")
    save_ledger(cleaned, path)
    print(f"[ok] ledger={path} removidas={removed} total_final={len(cleaned)}")


if __name__ == "__main__":
    main()
