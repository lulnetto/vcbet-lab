from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from vcbet.core.market_normalizer import detect_market_scope, normalize_market_entry


class MarketNormalizerTest(unittest.TestCase):
    def test_primeiro_tempo_is_not_normalized_as_full_time(self) -> None:
        normalized = normalize_market_entry(
            market_raw="Total de Gols Mais/Menos - Primeiro Tempo",
            selection_raw="Mais de 0.5",
            home_team="Casa",
            away_team="Fora",
        )

        self.assertNotEqual(normalized["market_scope"], "full_time")
        self.assertEqual(normalized["normalized_status"], "unsupported_scope")

    def test_supported_half_scope_terms_are_recognized(self) -> None:
        expected = {
            "1º tempo": "first_half",
            "1° tempo": "first_half",
            "1 tempo": "first_half",
            "segundo tempo": "second_half",
            "2º tempo": "second_half",
            "2 tempo": "second_half",
        }

        for term, scope in expected.items():
            with self.subTest(term=term):
                self.assertEqual(detect_market_scope(f"total de gols mais/menos - {term}"), scope)

    def test_half_scope_rows_are_ignored_not_promoted_to_full_time(self) -> None:
        normalized = normalize_market_entry(
            market_raw="Total de Gols Mais/Menos - 1º tempo",
            selection_raw="Mais de 0.5",
            home_team="Casa",
            away_team="Fora",
        )

        self.assertEqual(normalized["market_scope"], "first_half")
        self.assertEqual(normalized["normalized_status"], "ignored_market")
        self.assertIsNone(normalized["market_type"])

    def test_unsupported_scope_does_not_continue_as_full_time(self) -> None:
        normalized = normalize_market_entry(
            market_raw="Total de Gols Mais/Menos - Tempo Extra",
            selection_raw="Mais de 0.5",
            home_team="Casa",
            away_team="Fora",
        )

        self.assertIsNone(normalized["market_scope"])
        self.assertEqual(normalized["normalized_status"], "unsupported_scope")
        self.assertIsNone(normalized["market_type"])

    def test_asian_handicap_team_name_starting_with_number_uses_suffix_line(self) -> None:
        normalized = normalize_market_entry(
            market_raw="Handicap Asiático",
            selection_raw="3 de Febrero +0.5",
            home_team="3 de Febrero",
            away_team="Sol de America",
        )

        self.assertEqual(normalized["normalized_status"], "ok")
        self.assertEqual(normalized["market_type"], "asian_handicap")
        self.assertEqual(normalized["target_team_role"], "home")
        self.assertEqual(normalized["side"], "home")
        self.assertEqual(normalized["line"], 0.5)

    def test_asian_handicap_lines_are_parsed_from_final_numeric_token(self) -> None:
        cases = {
            "0": 0.0,
            "0.0": 0.0,
            "+0": 0.0,
            "-0": -0.0,
            "+0.5": 0.5,
            "-0.25": -0.25,
        }

        for raw_line, expected in cases.items():
            with self.subTest(raw_line=raw_line):
                normalized = normalize_market_entry(
                    market_raw="Handicap Asiático",
                    selection_raw=f"11 Deportivo {raw_line}",
                    home_team="11 Deportivo",
                    away_team="FAS",
                )

                self.assertEqual(normalized["normalized_status"], "ok")
                self.assertEqual(normalized["target_team_role"], "home")
                self.assertEqual(normalized["line"], expected)
                if raw_line == "-0":
                    self.assertLess(math.copysign(1.0, normalized["line"]), 0)

    def test_snapshot_loader_refreshes_stale_normalized_columns(self) -> None:
        try:
            from vcbet.core.pipeline_ev import carregar_snapshot_odds
        except ModuleNotFoundError as exc:
            self.skipTest(f"pipeline dependencies unavailable: {exc}")

        content = (
            "league;match_datetime;match_name;home_team;away_team;market_raw;selection_raw;odd;"
            "market_type;market_scope;side;line;target_team_role;target_team_name;normalized_status\n"
            "Liga;2026-04-24 15:00;Casa - Fora;Casa;Fora;"
            "Handicap Asiático - Primeiro Tempo  (Resultado atual 0 - 0);Casa +0.5;1.90;"
            "asian_handicap;full_time;home;0.5;home;Casa;ok\n"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            odds_file = Path(tmp_dir) / "odds_snapshot.csv"
            odds_file.write_text(content, encoding="utf-8")

            loaded = carregar_snapshot_odds(odds_file)

        row = loaded.iloc[0]
        self.assertIsNone(row["market_type"])
        self.assertNotEqual(row["market_scope"], "full_time")
        self.assertEqual(row["normalized_status"], "unsupported_scope")


if __name__ == "__main__":
    unittest.main()
