"""Testes para o backfill conservador de FotMob no registry."""
import csv
import os
import tempfile
import unittest
from pathlib import Path

from vcbet.team_identity.registry_repository import APPROVED_COLUMNS


class SyncFotmobRegistryTest(unittest.TestCase):
    def _run_script(self, registry_rows, snapshot_rows, args):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "registry.csv"
            snapshot_path = tmp_path / "xg_snapshot.csv"

            with registry_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=APPROVED_COLUMNS, delimiter=";")
                writer.writeheader()
                writer.writerows(registry_rows)

            with snapshot_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "run_id", "collected_at", "source", "league", "team_name",
                        "xg", "xga", "xg_home", "xg_away", "xga_home", "xga_away",
                        "xg_split_method", "source_team_id", "source_data_provider",
                        "fotmob_league_id", "fotmob_ccode3", "xg_raw_total", "xga_raw_total",
                        "xpoints", "goals_home_per_match", "goals_away_per_match",
                        "goals_for_per_match", "goals_against_per_match", "short_name",
                    ],
                    delimiter=";",
                )
                writer.writeheader()
                writer.writerows(snapshot_rows)

            cmd = [
                sys.executable,
                "scripts/sync_fotmob_registry.py",
                "--project-root", str(tmp_path),
                "--registry", str(registry_path),
                "--xg-file", str(snapshot_path),
                *args,
            ]
            env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent, env=env)
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            report_path = tmp_path / "data" / "team_registry" / "fotmob_registry_sync_report.csv"
            report = []
            if report_path.exists():
                with report_path.open("r", newline="", encoding="utf-8-sig") as fh:
                    report = list(csv.DictReader(fh, delimiter=";"))

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                final_rows = list(csv.DictReader(fh, delimiter=";"))

            return report, final_rows

    def _make_registry_row(self, **kwargs):
        defaults = {col: "" for col in APPROVED_COLUMNS}
        defaults["match_status"] = "MATCH_REGISTRY_APPROVED"
        defaults["match_confidence"] = "1.0000"
        defaults["match_method"] = "registry_auto_strict"
        defaults["approved_at"] = "2026-04-25 10:00:00"
        defaults["source"] = "ui_review"
        defaults.update(kwargs)
        return defaults

    def _make_snapshot_row(self, league, team_name, team_id, short_name=""):
        return {
            "run_id": "daily",
            "collected_at": "2026-04-29 10:00:00",
            "source": "fotmob",
            "league": league,
            "team_name": team_name,
            "xg": "1.0", "xga": "1.0", "xg_home": "1.0", "xg_away": "1.0",
            "xga_home": "1.0", "xga_away": "1.0", "xg_split_method": "fotmob_global",
            "source_team_id": str(team_id),
            "source_data_provider": "opta",
            "fotmob_league_id": "1",
            "fotmob_ccode3": "TST",
            "xg_raw_total": "10", "xga_raw_total": "10", "xpoints": "10",
            "goals_home_per_match": "1", "goals_away_per_match": "1",
            "goals_for_per_match": "1", "goals_against_per_match": "1",
            "short_name": short_name,
        }

    def test_inter_de_milao_does_not_match_milan(self):
        registry = [
            self._make_registry_row(league="Serie A", betano_name="Inter de Milão", footystats_name="AC Milan"),
        ]
        snapshot = [
            self._make_snapshot_row(league="Serie A", team_name="Milan", team_id="8564"),
        ]
        report, final = self._run_script(registry, snapshot, ["--dry-run"])
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["status"], "no_match")
        self.assertEqual(report[0]["reason"], "denylist_protected")

    def test_los_angeles_galaxy_does_not_match_lafc(self):
        registry = [
            self._make_registry_row(league="MLS", betano_name="Los Angeles Galaxy", footystats_name="Los Angeles FC"),
        ]
        snapshot = [
            self._make_snapshot_row(league="MLS", team_name="Los Angeles FC", team_id="867280"),
        ]
        report, final = self._run_script(registry, snapshot, ["--dry-run"])
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["status"], "no_match")
        self.assertEqual(report[0]["reason"], "denylist_protected")

    def test_exact_match_updates(self):
        registry = [
            self._make_registry_row(league="Premier League", betano_name="Arsenal", footystats_name="Arsenal"),
        ]
        snapshot = [
            self._make_snapshot_row(league="Premier League", team_name="Arsenal", team_id="9825"),
        ]
        report, final = self._run_script(registry, snapshot, ["--apply"])
        self.assertEqual(report[0]["status"], "safe_exact")
        self.assertEqual(final[0]["fotmob_team_id"], "9825")
        self.assertEqual(final[0]["fotmob_team_name"], "Arsenal")
        self.assertEqual(final[0]["xg_provider_preferred"], "fotmob")

    def test_ambiguous_match_does_not_update(self):
        registry = [
            self._make_registry_row(league="Ligue 1", betano_name="Paris FC", footystats_name="Paris Saint-Germain FC"),
        ]
        snapshot = [
            self._make_snapshot_row(league="Ligue 1", team_name="Paris Saint-Germain", team_id="9847"),
            self._make_snapshot_row(league="Ligue 1", team_name="Paris FC", team_id="6379"),
        ]
        report, final = self._run_script(registry, snapshot, ["--apply"])
        self.assertEqual(report[0]["status"], "ambiguous_match")
        self.assertEqual(final[0]["fotmob_team_id"], "")

    def test_dry_run_does_not_modify_csv(self):
        registry = [
            self._make_registry_row(league="Premier League", betano_name="Arsenal", footystats_name="Arsenal"),
        ]
        snapshot = [
            self._make_snapshot_row(league="Premier League", team_name="Arsenal", team_id="9825"),
        ]
        report, final = self._run_script(registry, snapshot, ["--dry-run"])
        self.assertEqual(report[0]["status"], "safe_exact")
        self.assertEqual(final[0]["fotmob_team_id"], "")

    def test_apply_only_safe_exact(self):
        registry = [
            self._make_registry_row(league="Premier League", betano_name="Arsenal", footystats_name="Arsenal"),
            self._make_registry_row(league="Ligue 1", betano_name="Paris FC", footystats_name="Paris Saint-Germain FC"),
        ]
        snapshot = [
            self._make_snapshot_row(league="Premier League", team_name="Arsenal", team_id="9825"),
            self._make_snapshot_row(league="Ligue 1", team_name="Paris Saint-Germain", team_id="9847"),
            self._make_snapshot_row(league="Ligue 1", team_name="Paris FC", team_id="6379"),
        ]
        report, final = self._run_script(registry, snapshot, ["--apply"])
        statuses = {r["betano_name"]: r["status"] for r in report}
        self.assertEqual(statuses["Arsenal"], "safe_exact")
        self.assertEqual(statuses["Paris FC"], "ambiguous_match")
        self.assertEqual(final[0]["fotmob_team_id"], "9825")
        self.assertEqual(final[1]["fotmob_team_id"], "")

    def test_already_filled_is_skipped(self):
        registry = [
            self._make_registry_row(
                league="La Liga", betano_name="Athletic Bilbao", footystats_name="Athletic Club",
                fotmob_team_name="Athletic Club", fotmob_team_id="8315", xg_provider_preferred="fotmob",
            ),
        ]
        snapshot = [
            self._make_snapshot_row(league="La Liga", team_name="Athletic Club", team_id="8315"),
        ]
        report, final = self._run_script(registry, snapshot, ["--apply"])
        self.assertEqual(report[0]["status"], "already_filled")
        self.assertEqual(final[0]["fotmob_team_id"], "8315")


if __name__ == "__main__":
    unittest.main()
