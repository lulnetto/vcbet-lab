from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from vcbet.service.dashboard import apply_filters
from vcbet.service.commands import build_daily_commands, build_results_settlement_commands
from vcbet.service.schemas import DailyRunRequest, ResultsSettlementRequest


class ServiceComposedWorkflowTest(unittest.TestCase):
    def test_results_settlement_cycle_keeps_results_and_settlement_as_separate_phases(self) -> None:
        commands = build_results_settlement_commands(
            Path("/tmp/vcbet"),
            ResultsSettlementRequest(
                ledger_file="data/history/bets_ledger.csv",
                results_file="data/results/results_auto.csv",
            ),
        )

        self.assertEqual([cmd.name for cmd in commands], ["results_collection", "settlement"])

    def test_daily_cycle_excludes_closing_odds_by_default_and_refreshes_catalogs(self) -> None:
        commands = build_daily_commands(
            Path("/tmp/vcbet"),
            DailyRunRequest(date="2026-04-24", config_name="legacy_v2"),
        )
        names = [cmd.name for cmd in commands]

        self.assertIn("analysis", names)
        self.assertIn("results_collection", names)
        self.assertIn("settlement", names)
        self.assertIn("refresh_run_catalog", names)
        self.assertIn("refresh_replay_catalog", names)
        self.assertNotIn("closing_odds", names)
        self.assertLess(names.index("analysis"), names.index("refresh_run_catalog"))

    def test_dashboard_date_filter_prefers_event_date_over_created_at(self) -> None:
        df = pd.DataFrame(
            [
                {"bet_id": "today", "match_datetime": "2026-04-25 21:30:00", "created_at": "2026-04-24 23:10:00"},
                {"bet_id": "old", "match_datetime": "2026-04-24 21:30:00", "created_at": "2026-04-25 01:10:00"},
                {"bet_id": "missing-date", "created_at": "2026-04-20 01:10:00"},
            ]
        )

        filtered = apply_filters(df, date_from="2026-04-25", date_to="2026-04-25")

        self.assertEqual(set(filtered["bet_id"]), {"today", "missing-date"})


if __name__ == "__main__":
    unittest.main()
