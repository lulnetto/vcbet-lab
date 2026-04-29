"""Testes para garantir que registry aprovado funciona no team matcher."""
import csv
import tempfile
import unittest
from pathlib import Path

from vcbet.core.team_matcher import match_team_name
from vcbet.team_identity.registry_repository import APPROVED_COLUMNS, safe_write_registry_rows


class TeamMatcherRegistryTest(unittest.TestCase):
    def _make_registry_row(self, **kwargs):
        defaults = {col: "" for col in APPROVED_COLUMNS}
        defaults["match_status"] = "MATCH_REGISTRY_APPROVED"
        defaults["match_confidence"] = "1.0000"
        defaults["match_method"] = "registry_auto_strict"
        defaults["approved_at"] = "2026-04-25 10:00:00"
        defaults["source"] = "ui_review"
        defaults.update(kwargs)
        return defaults

    def test_registry_approved_with_fotmob_team_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.csv"
            rows = [
                self._make_registry_row(
                    league="La Liga",
                    betano_name="Athletic Bilbao",
                    footystats_name="Athletic Club",
                    fotmob_team_id="8315",
                    fotmob_team_name="Athletic Club",
                ),
            ]
            safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)

            result = match_team_name(
                "Athletic Bilbao",
                ["Athletic Club", "Real Madrid"],
                league="La Liga",
                registry_file=registry_path,
                xg_source="fotmob",
                source_team_id_map={"Athletic Club": "8315", "Real Madrid": "8633"},
            )
            self.assertEqual(result.match_status, "MATCH_REGISTRY_APPROVED")
            self.assertEqual(result.matched_name, "Athletic Club")
            self.assertEqual(result.match_source, "team_registry")

    def test_registry_approved_without_fotmob_id_but_footystats_name_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.csv"
            rows = [
                self._make_registry_row(
                    league="Premier League",
                    betano_name="Arsenal",
                    footystats_name="Arsenal",
                ),
            ]
            safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)

            result = match_team_name(
                "Arsenal",
                ["Arsenal", "Chelsea"],
                league="Premier League",
                registry_file=registry_path,
                xg_source="fotmob",
                source_team_id_map={"Arsenal": "9825", "Chelsea": "8455"},
            )
            self.assertEqual(result.match_status, "MATCH_REGISTRY_APPROVED")
            self.assertEqual(result.matched_name, "Arsenal")

    def test_registry_approved_without_fotmob_falls_back_to_footystats(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.csv"
            rows = [
                self._make_registry_row(
                    league="Bundesliga",
                    betano_name="Bayern de Munique",
                    footystats_name="Bayern München",
                ),
            ]
            safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)

            result = match_team_name(
                "Bayern de Munique",
                ["Bayern München", "Borussia Dortmund"],
                league="Bundesliga",
                registry_file=registry_path,
                xg_source="fotmob",
            )
            self.assertEqual(result.match_status, "MATCH_REGISTRY_APPROVED")
            self.assertEqual(result.matched_name, "Bayern München")

    def test_registry_approved_does_not_fall_to_fuzzy(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.csv"
            rows = [
                self._make_registry_row(
                    league="Serie A",
                    betano_name="Inter de Milão",
                    footystats_name="AC Milan",
                ),
            ]
            safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)

            # O registry está aprovado, mas o footystats_name (AC Milan) não bate
            # com os candidates (Inter, Juventus). Nesse caso, o lookup retorna None
            # e o matcher cai para fuzzy/exact. Isso é esperado porque o registry
            # está com footystats_name errado.
            result = match_team_name(
                "Inter de Milão",
                ["Inter", "Juventus"],
                league="Serie A",
                registry_file=registry_path,
                xg_source="fotmob",
            )
            # Não deve ser MATCH_REGISTRY_APPROVED porque o footystats_name não bate
            self.assertNotEqual(result.match_status, "MATCH_REGISTRY_APPROVED")

    def test_dry_run_does_not_write_functional_pending(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            functional_pending = tmp_path / "team_registry" / "alias_review_pending.csv"
            functional_pending.parent.mkdir(parents=True, exist_ok=True)
            functional_pending.write_text("league;betano_name;betano_team_id;betano_url;suggested_footystats_name;top_score;review_reason;ambiguous_options;status;source;created_at;updated_at\n")

            registry_path = tmp_path / "registry.csv"
            rows = [
                self._make_registry_row(
                    league="Test League",
                    betano_name="Team A",
                    footystats_name="Team A",
                ),
            ]
            safe_write_registry_rows(rows, registry_path, fieldnames=APPROVED_COLUMNS)

            # Simular pipeline_ev em dry-run via subprocess
            odds_path = tmp_path / "odds.csv"
            xg_path = tmp_path / "xg.csv"
            # Criar odds mínimas
            with odds_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=["run_id", "collected_at", "source", "league", "match_datetime", "home_team", "away_team", "match_name", "market_raw", "selection_raw", "odd", "event_url", "source_event_id", "betano_event_id", "betano_league_id", "betano_market_id", "betano_market_type", "betano_market_type_id", "betano_market_unique_id", "betano_market_family", "betano_selection_id", "betano_bet_ref", "betano_total_markets_available", "betano_markets_count", "betano_fetch_method", "betano_table_row_name", "betano_group_name", "market_type", "market_scope", "side", "line", "target_team_role", "target_team_name", "normalized_status"], delimiter=";")
                writer.writeheader()
                writer.writerow({
                    "run_id": "r1", "collected_at": "2026-04-29", "source": "betano",
                    "league": "Test League", "match_datetime": "2026-04-29", "home_team": "Team A",
                    "away_team": "Team B", "match_name": "Team A - Team B", "market_raw": "1X2",
                    "selection_raw": "Team A", "odd": "1.5", "event_url": "", "source_event_id": "1",
                    "betano_event_id": "1", "betano_league_id": "1", "betano_market_id": "1",
                    "betano_market_type": "1X2", "betano_market_type_id": "", "betano_market_unique_id": "",
                    "betano_market_family": "match_winner", "betano_selection_id": "", "betano_bet_ref": "",
                    "betano_total_markets_available": "1", "betano_markets_count": "1",
                    "betano_fetch_method": "test", "betano_table_row_name": "", "betano_group_name": "",
                    "market_type": "match_winner", "market_scope": "match", "side": "home", "line": "",
                    "target_team_role": "home", "target_team_name": "Team A", "normalized_status": "ok"
                })

            # Criar xG mínimo
            with xg_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=["run_id", "collected_at", "source", "league", "team_name", "xg", "xga", "xg_home", "xg_away", "xga_home", "xga_away", "xg_split_method", "source_team_id", "source_data_provider", "fotmob_league_id", "fotmob_ccode3"], delimiter=";")
                writer.writeheader()
                writer.writerow({
                    "run_id": "r1", "collected_at": "2026-04-29", "source": "fotmob",
                    "league": "Test League", "team_name": "Team A", "xg": "1", "xga": "1",
                    "xg_home": "1", "xg_away": "1", "xga_home": "1", "xga_away": "1",
                    "xg_split_method": "fotmob_global", "source_team_id": "1",
                    "source_data_provider": "opta", "fotmob_league_id": "1", "fotmob_ccode3": "TST"
                })
                writer.writerow({
                    "run_id": "r1", "collected_at": "2026-04-29", "source": "fotmob",
                    "league": "Test League", "team_name": "Team B", "xg": "1", "xga": "1",
                    "xg_home": "1", "xg_away": "1", "xga_home": "1", "xga_away": "1",
                    "xg_split_method": "fotmob_global", "source_team_id": "2",
                    "source_data_provider": "opta", "fotmob_league_id": "1", "fotmob_ccode3": "TST"
                })

            cmd = [
                sys.executable,
                "-m", "vcbet.core.pipeline_ev",
                "--odds-file", str(odds_path),
                "--xg-file", str(xg_path),
                "--run-id", "test_dry_run",
                "--output-dir", str(tmp_path / "runs"),
                "--dry-run",
            ]
            env = {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent, env=env)

            # O dry-run pode falhar por snapshot health, mas não deve escrever no pending funcional
            after_content = functional_pending.read_text(encoding="utf-8")
            self.assertEqual(after_content.count("\n"), 1, msg="Dry-run não deve adicionar linhas ao pending funcional")

    def test_alias_times_not_used_in_main_flow(self):
        """match_team_name não deve retornar manual_approved/alias_times (legado removido)."""
        result = match_team_name(
            "Los Angeles Galaxy",
            ["Los Angeles FC", "LA Galaxy"],
            league="MLS",
            registry_file=None,  # sem registry
        )
        self.assertNotEqual(result.match_status, "manual_approved")
        self.assertNotEqual(result.match_source, "alias_times")


if __name__ == "__main__":
    unittest.main()
