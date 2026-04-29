"""Testes para o fluxo UI/backend de aprovação/rejeição do team registry."""
import csv
import tempfile
import unittest
from pathlib import Path

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

    def test_auto_strict_without_betano_id_gets_quarantined(self):
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
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(result.stdout.strip(), "1")

            with registry_path.open("r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(rows), 0)

            self.assertTrue(quarantine_path.exists())
            with quarantine_path.open("r", newline="", encoding="utf-8-sig") as fh:
                qrows = list(csv.DictReader(fh, delimiter=";"))
            self.assertEqual(len(qrows), 1)
            self.assertEqual(qrows[0]["betano_name"], "Athletic Bilbao")
            self.assertEqual(qrows[0]["quarantine_reason"], "invalid_betano_team_identity")


if __name__ == "__main__":
    unittest.main()
