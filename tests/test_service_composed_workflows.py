from __future__ import annotations

from datetime import datetime
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

import pandas as pd

from vcbet.service.dashboard import apply_filters
from vcbet.service.commands import build_daily_commands, build_reconcile_unmatched_command, build_results_settlement_commands
from vcbet.service.job_store import JobStore
from vcbet.service.schemas import DailyRunRequest, ReconcileUnmatchedRequest, ResultsSettlementRequest
from vcbet.service.schemas import JobRecord


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

    def test_reconcile_unmatched_command_calls_retry_script(self) -> None:
        command = build_reconcile_unmatched_command(
            Path("/tmp/vcbet"),
            ReconcileUnmatchedRequest(
                ledger_file="data/history/bets_ledger.csv",
                results_file="data/results/results_unmatched_retry.csv",
                max_pages=12,
                source="api",
                debug=True,
                no_overrides=True,
            ),
        )

        self.assertEqual(command.name, "reconcile_unmatched")
        self.assertIn("/tmp/vcbet/scripts/retry_unmatched_settlement.py", command.command)
        self.assertIn("--source", command.command)
        self.assertIn("api", command.command)
        self.assertIn("--debug", command.command)
        self.assertIn("--no-overrides", command.command)

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

    def test_job_store_save_is_atomic_and_preserves_existing_json_on_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            queued = JobRecord(
                id="job_atomic",
                job_type="analysis",
                status="queued",
                title="Atomic save",
                created_at=datetime(2026, 4, 24, 12, 0, 0),
            )
            running = queued.model_copy(update={"status": "running"}) if hasattr(queued, "model_copy") else queued.copy(update={"status": "running"})

            store.save(queued)
            with patch("vcbet.service.job_store.os.replace", side_effect=RuntimeError("replace failed")):
                with self.assertRaisesRegex(RuntimeError, "replace failed"):
                    store.save(running)

            loaded = store.load("job_atomic")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.status, "queued")
            self.assertEqual([path.name for path in Path(tmp).glob("*.tmp")], [])


if __name__ == "__main__":
    unittest.main()
