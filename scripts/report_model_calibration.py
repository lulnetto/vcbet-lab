#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from vcbet.paths import DEFAULT_LEDGER_FILE
from vcbet.reports.model_calibration import build_report_from_ledger, format_calibration_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reporta calibracao de prob_model contra frequencias realizadas.")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE))
    parser.add_argument("--min-league-settled", type=int, default=30)
    parser.add_argument("--bin-size", type=float, default=0.10)
    parser.add_argument("--output", help="Caminho opcional para gravar o relatorio Markdown.")
    args = parser.parse_args(argv)

    report = build_report_from_ledger(
        args.ledger_file,
        min_league_settled=args.min_league_settled,
        bin_size=args.bin_size,
    )
    rendered = format_calibration_report(report)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
