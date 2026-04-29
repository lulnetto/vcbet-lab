"""Testes para o fluxo UI/backend de aprovação/rejeição do team registry."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vcbet.team_identity.registry_repository import APPROVED_COLUMNS, safe_write_registry_rows
from vcbet.team_identity.review_writer import REVIEW_COLUMNS


class TeamRegistryUiTest(unittest.TestCase):
    def _make_registry_row(self, **kwargs):
        defaults = {col: "" for col in APPROVED_COLUMNS}
        defaults["match_status"] = "MATCH_REGISTRY_APPROVED"
        defaults["match_confidence"] = "1.0000"
        defaults["match_method"] = "registry_auto_strict"
        defaults["approved_at"] = "2026-04-25 10:00:00"
        defaults["source"] = "ui_review"
        defaults.update(kwargs)
        return defaults

    def _make_pending_row(self, **kwargs):
        defaults = {col: "" for col in REVIEW_COLUMNS}
        defaults["status"] = "pending_review"
        defaults["source"] = "pipeline"
        defaults.update(kwargs)
        return defaults

    def _write_pending_rows(self, pending_path, rows):
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        with pending_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def _write_xg_snapshot(self, xg_path, rows):
        xg_path.parent.mkdir(parents=True, exist_ok=True)
        with xg_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["league", "team_name", "source", "source_team_id"], delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def test_latest_daily_xg_snapshot_uses_date_folder_not_runs(self):
        from vcbet.service.team_registry_api import latest_daily_xg_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            older = tmp_path / "data" / "xg" / "2026-04-28" / "xg_snapshot.csv"
            newer = tmp_path / "data" / "xg" / "2026-04-29" / "xg_snapshot.csv"
            runs = tmp_path / "data" / "runs" / "2026-05-01" / "run_x" / "xg_snapshot.csv"
            for path in (older, newer, runs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("league;team_name;source;source_team_id\n", encoding="utf-8")

            self.assertEqual(latest_daily_xg_snapshot(tmp_path), newer.resolve())

    def test_approve_pending_enriches_fotmob_from_daily_xg(self):
        from vcbet.service.team_registry_api import approve_registry_alias

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pending_path = tmp_path / "data" / "team_registry" / "alias_review_pending.csv"
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            xg_path = tmp_path / "data" / "xg" / "2026-04-29" / "xg_snapshot.csv"

            self._write_pending_rows(pending_path, [
                self._make_pending_row(
                    league="Serie A",
                    betano_name="Inter de Milão",
                    suggested_footystats_name="Inter",
                ),
            ])
            self._write_xg_snapshot(xg_path, [
                {"league": "Serie A", "team_name": "Inter", "source": "fotmob", "source_team_id": "8636"},
            ])

            result = approve_registry_alias(tmp_path, {
                "league": "Serie A",
                "betano_name": "Inter de Milão",
                "footystats_name": "Inter",
            })

            self.assertEqual(result["added"], 1)
            self.assertEqual(result["resolved_pending"], 1)
            self.assertTrue(result["fotmob_enriched"])
            self.assertEqual(result["fotmob_enrichment_reason"], "matched")
            self.assertEqual(result["xg_file_used"], str(xg_path.resolve()))

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["fotmob_team_name"], "Inter")
            self.assertEqual(rows[0]["fotmob_team_id"], "8636")
            self.assertEqual(rows[0]["xg_provider_preferred"], "fotmob")
            self.assertEqual(rows[0]["canonical_team_name"], "Inter")

    def test_approve_duplicate_updates_empty_fotmob_fields(self):
        from vcbet.service.team_registry_api import approve_registry_alias

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            pending_path = tmp_path / "data" / "team_registry" / "alias_review_pending.csv"
            xg_path = tmp_path / "data" / "xg" / "2026-04-29" / "xg_snapshot.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)

            registry_rows = [
                self._make_registry_row(
                    league="Serie A",
                    betano_name="Inter de Milão",
                    footystats_name="FC Internazionale Milano",
                    fotmob_team_name="",
                    fotmob_team_id="",
                    canonical_team_name="",
                ),
            ]
            safe_write_registry_rows(registry_rows, registry_path, fieldnames=APPROVED_COLUMNS)
            self._write_pending_rows(pending_path, [
                self._make_pending_row(
                    league="Serie A",
                    betano_name="Inter de Milão",
                    suggested_footystats_name="Inter",
                ),
            ])
            self._write_xg_snapshot(xg_path, [
                {"league": "Serie A", "team_name": "Inter", "source": "fotmob", "source_team_id": "8636"},
            ])

            result = approve_registry_alias(tmp_path, {
                "league": "Serie A",
                "betano_name": "Inter de Milão",
                "footystats_name": "Inter",
            })

            self.assertEqual(result["added"], 0)
            self.assertEqual(result["updated_existing"], 1)
            self.assertEqual(result["resolved_pending"], 1)

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["footystats_name"], "FC Internazionale Milano")
            self.assertEqual(rows[0]["match_status"], "MATCH_REGISTRY_APPROVED")
            self.assertEqual(rows[0]["fotmob_team_name"], "Inter")
            self.assertEqual(rows[0]["fotmob_team_id"], "8636")
            self.assertEqual(rows[0]["xg_provider_preferred"], "fotmob")
            self.assertEqual(rows[0]["canonical_team_name"], "Inter")

            with pending_path.open("r", newline="", encoding="utf-8-sig") as fh:
                pending_rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(pending_rows), 0)

    def test_sync_all_registry_leagues_passes_latest_daily_xg(self):
        from vcbet.service.team_registry_api import sync_all_registry_leagues

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            older = tmp_path / "data" / "xg" / "2026-04-28" / "xg_snapshot.csv"
            newer = tmp_path / "data" / "xg" / "2026-04-29" / "xg_snapshot.csv"
            runs = tmp_path / "data" / "runs" / "2026-05-01" / "run_x" / "xg_snapshot.csv"
            for path in (older, newer, runs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("league;team_name;source;source_team_id\n", encoding="utf-8")

            captured_payloads = []

            def fake_sync_registry_league(project_root, payload):
                captured_payloads.append(payload)
                return {
                    "status": "ok",
                    "league": payload["league"],
                    "xg_file_used": str(payload.get("xg_file") or ""),
                }

            with patch("vcbet.service.team_registry_api.list_registry_leagues", return_value={"items": [{"name": "Serie A"}]}), \
                    patch("vcbet.service.team_registry_api.sync_registry_league", side_effect=fake_sync_registry_league):
                result = sync_all_registry_leagues(tmp_path, {})

            expected = str(newer.resolve())
            self.assertEqual(captured_payloads[0]["xg_file"], expected)
            self.assertEqual(result["xg_file_used"], expected)
            self.assertEqual(result["xg_source_policy"], "latest_daily_xg_snapshot")
            self.assertEqual(result["items"][0]["xg_file_used"], expected)
            self.assertNotIn("data/runs", captured_payloads[0]["xg_file"])

    def test_backend_approves_pending_and_updates_registry(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            pending_path = tmp_path / "data" / "team_registry" / "alias_review_pending.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.parent.mkdir(parents=True, exist_ok=True)

            registry_rows = [
                self._make_registry_row(
                    league="La Liga",
                    betano_name="Real Madrid",
                    footystats_name="Real Madrid",
                ),
            ]
            safe_write_registry_rows(registry_rows, registry_path, fieldnames=APPROVED_COLUMNS)

            pending_rows = [
                self._make_pending_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    suggested_footystats_name="Athletic Club",
                    top_score="95",
                    review_reason="pending_review: match_requires_registry_review",
                ),
            ]
            with pending_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, delimiter=";")
                writer.writeheader()
                writer.writerows(pending_rows)

            cmd = [
                sys.executable,
                "-c",
                """
import sys
sys.path.insert(0, "/mnt/c/Users/Netto/Documents/VCBet")
from vcbet.service.team_registry_api import approve_registry_alias
from pathlib import Path
result = approve_registry_alias(Path(""" + repr(str(tmp_path)) + """), {
    "league": "La Liga",
    "betano_name": "Athletic Bilbao",
    "footystats_name": "Athletic Club",
    "suggested_footystats_name": "Athletic Club",
    "top_score": "95",
    "source": "ui_review",
    "fotmob_team_name": "Athletic Club",
    "fotmob_team_id": "8315",
    "xg_provider_preferred": "fotmob",
    "canonical_team_name": "Athletic Club",
})
print(result["added"])
print(result["resolved_pending"])
""",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            lines = result.stdout.strip().split("\n")
            self.assertEqual(lines[0], "1")
            self.assertEqual(lines[1], "1")

            # Verify registry has the new alias
            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            bilbao = [r for r in rows if r.get("betano_name") == "Athletic Bilbao"]
            self.assertEqual(len(bilbao), 1)
            self.assertEqual(bilbao[0]["footystats_name"], "Athletic Club")
            self.assertEqual(bilbao[0]["fotmob_team_id"], "8315")
            self.assertEqual(bilbao[0]["match_status"], "MATCH_REGISTRY_APPROVED")
            self.assertEqual(bilbao[0]["xg_provider_preferred"], "fotmob")

            # Verify pending is empty
            with pending_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 0)

    def test_approval_preserves_existing_footystats_name(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            pending_path = tmp_path / "data" / "team_registry" / "alias_review_pending.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.parent.mkdir(parents=True, exist_ok=True)

            registry_rows = [
                self._make_registry_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    footystats_name="Athletic Club",
                    fotmob_team_id="8315",
                ),
            ]
            safe_write_registry_rows(registry_rows, registry_path, fieldnames=APPROVED_COLUMNS)

            pending_rows = [
                self._make_pending_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    suggested_footystats_name="Athletic Club Bilbao",
                ),
            ]
            with pending_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, delimiter=";")
                writer.writeheader()
                writer.writerows(pending_rows)

            cmd = [
                sys.executable,
                "-c",
                """
import sys
sys.path.insert(0, "/mnt/c/Users/Netto/Documents/VCBet")
from vcbet.service.team_registry_api import approve_registry_alias
from pathlib import Path
result = approve_registry_alias(Path(""" + repr(str(tmp_path)) + """), {
    "league": "La Liga",
    "betano_name": "Athletic Bilbao",
    "footystats_name": "Athletic Club Bilbao",
})
print(result["added"])
""",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.strip(), "0")

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            bilbao = [r for r in rows if r.get("betano_name") == "Athletic Bilbao"]
            self.assertEqual(len(bilbao), 1)
            self.assertEqual(bilbao[0]["footystats_name"], "Athletic Club")

    def test_reject_does_not_alter_registry(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            pending_path = tmp_path / "data" / "team_registry" / "alias_review_pending.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.parent.mkdir(parents=True, exist_ok=True)

            registry_rows = [
                self._make_registry_row(
                    league="La Liga",
                    betano_name="Real Madrid",
                    footystats_name="Real Madrid",
                ),
            ]
            safe_write_registry_rows(registry_rows, registry_path, fieldnames=APPROVED_COLUMNS)

            pending_rows = [
                self._make_pending_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    suggested_footystats_name="Athletic Club",
                ),
            ]
            with pending_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, delimiter=";")
                writer.writeheader()
                writer.writerows(pending_rows)

            cmd = [
                sys.executable,
                "-c",
                """
import sys
sys.path.insert(0, "/mnt/c/Users/Netto/Documents/VCBet")
from vcbet.service.team_registry_api import reject_registry_alias
from pathlib import Path
result = reject_registry_alias(Path(""" + repr(str(tmp_path)) + """), {
    "league": "La Liga",
    "betano_name": "Athletic Bilbao",
})
print(result["rejected"])
""",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.strip(), "1")

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["betano_name"], "Real Madrid")

    def test_writer_keeps_semicolon_delimiter(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "registry.csv"
            rows = [
                self._make_registry_row(
                    league="Test",
                    betano_name="Team A",
                    footystats_name="Team A",
                ),
            ]
            safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)
            with registry_path.open("rb") as fh:
                data = fh.read()
            self.assertIn(b";", data)
            self.assertNotIn(b",Team A", data)

    def test_ui_approved_without_betano_id_stays_in_registry(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)

            registry_rows = [
                self._make_registry_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    footystats_name="Athletic Club",
                    betano_team_id="",
                    betano_url="",
                    match_method="registry_review",
                    source="ui_review",
                ),
            ]
            safe_write_registry_rows(registry_rows, registry_path, fieldnames=APPROVED_COLUMNS)

            cmd = [
                sys.executable,
                "-c",
                """
import sys
sys.path.insert(0, "/mnt/c/Users/Netto/Documents/VCBet")
from vcbet.service.team_registry_api import cleanup_invalid_approved_registry
from pathlib import Path
result = cleanup_invalid_approved_registry(Path(""" + repr(str(tmp_path)) + """))
print(result["removed"])
""",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.strip(), "0")

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["betano_name"], "Athletic Bilbao")

    def test_auto_strict_without_betano_id_refuses_truncating_registry(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            registry_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases.csv"
            quarantine_path = tmp_path / "configs" / "team_registry" / "betano_footystats_aliases_quarantine.csv"
            registry_path.parent.mkdir(parents=True, exist_ok=True)

            registry_rows = [
                self._make_registry_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    footystats_name="Athletic Club",
                    betano_team_id="",
                    betano_url="",
                    match_method="registry_auto_strict",
                    source="sync_team_aliases",
                ),
            ]
            safe_write_registry_rows(registry_rows, registry_path, fieldnames=APPROVED_COLUMNS)

            cmd = [
                sys.executable,
                "-c",
                """
import sys
sys.path.insert(0, "/mnt/c/Users/Netto/Documents/VCBet")
from vcbet.service.team_registry_api import cleanup_invalid_approved_registry
from pathlib import Path
result = cleanup_invalid_approved_registry(Path(""" + repr(str(tmp_path)) + """))
print(result["removed"])
""",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Registry não será truncado", result.stderr)

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["league"], "La Liga")
            self.assertEqual(rows[0]["betano_name"], "Athletic Bilbao")
            self.assertEqual(rows[0]["match_method"], "registry_auto_strict")
            self.assertFalse(quarantine_path.exists())


if __name__ == "__main__":
    unittest.main()
