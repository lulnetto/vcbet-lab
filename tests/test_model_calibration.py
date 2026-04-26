from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from scripts.report_model_calibration import main as calibration_main
from vcbet.domain.contracts import BetRecord
from vcbet.reports.model_calibration import build_calibration_report, format_calibration_report


def record(index: int, *, league: str = "Liga Teste", prob: float = 0.65, status: str = "win") -> BetRecord:
    return BetRecord(
        bet_id=f"bet_{index}",
        league=league,
        final_bet_status="settled",
        final_settlement_status=status,
        prob_model=prob,
    )


class ModelCalibrationTest(unittest.TestCase):
    def test_bucket_logic_uses_model_probabilities_and_realized_frequency(self) -> None:
        records = []
        records.extend(record(i, prob=0.64, status="win") for i in range(16))
        records.extend(record(i + 16, prob=0.66, status="loss") for i in range(14))
        records.append(record(31, prob=0.82, status="half_win"))

        report = build_calibration_report(records, min_league_settled=30, bin_size=0.10)

        self.assertEqual(len(report.leagues), 1)
        league = report.leagues[0]
        self.assertEqual(league.settled_count, 31)
        self.assertEqual(league.eligible_count, 31)
        first_bucket = league.buckets[0]
        self.assertEqual((first_bucket.lower, first_bucket.upper), (0.6, 0.7))
        self.assertEqual(first_bucket.count, 30)
        self.assertAlmostEqual(first_bucket.avg_prob, 0.649333, places=6)
        self.assertAlmostEqual(first_bucket.observed_frequency, 16 / 30, places=6)

    def test_insufficient_sample_is_reported_explicitly(self) -> None:
        records = [record(i, league="Liga Curta", status="win") for i in range(30)]

        report = build_calibration_report(records, min_league_settled=30)
        rendered = format_calibration_report(report)

        self.assertEqual(report.leagues, ())
        self.assertEqual(report.insufficient_leagues, (("Liga Curta", 30),))
        self.assertIn("Calibration sample is insufficient", rendered)
        self.assertIn("Liga Curta: settled_records=30", rendered)

    def test_report_command_does_not_mutate_input_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "bets_ledger.csv"
            rows = [
                {
                    "bet_id": f"bet_{idx}",
                    "run_id": "run_calibration",
                    "league": "Liga Teste",
                    "match_datetime": "2026-04-24 15:00",
                    "home_team": "Casa FC",
                    "away_team": "Fora FC",
                    "match_name": f"Casa FC - Fora FC {idx}",
                    "market_type": "total_goals",
                    "market_scope": "full_time",
                    "side": "over",
                    "line": 2.5,
                    "selection_raw": "Mais de 2.5",
                    "odd_entrada": 2.0,
                    "stake_units": 1.0,
                    "prob_model": 0.62,
                    "final_bet_status": "settled",
                    "final_settlement_status": "win" if idx % 2 == 0 else "loss",
                }
                for idx in range(4)
            ]
            pd.DataFrame(rows).to_csv(ledger_file, index=False, sep=";", encoding="utf-8-sig")
            before = ledger_file.read_bytes()

            with redirect_stdout(io.StringIO()):
                exit_code = calibration_main([
                    "--ledger-file",
                    str(ledger_file),
                    "--min-league-settled",
                    "1",
                ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(ledger_file.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
