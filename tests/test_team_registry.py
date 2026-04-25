from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vcbet.core.team_matcher import match_team_name
from vcbet.core.team_registry import (
    BetanoTeam,
    build_registry_matches,
    normalize_team_name,
    parse_betano_standings_html,
    write_registry_aliases,
)


class TeamRegistryTest(unittest.TestCase):
    def test_normalization_handles_translations_and_suffixes(self) -> None:
        self.assertEqual(normalize_team_name("Bayern de Munique FC"), "bayern munich")
        self.assertEqual(normalize_team_name("1. FC Köln"), "1 cologne")

    def test_parse_betano_standings_html_extracts_team_names_and_ids(self) -> None:
        html = """
        <a href="/sport/futebol/alemanha/bundesliga/bayern-de-munique/12345/">Bayern de Munique</a>
        <a href="/sport/futebol/alemanha/bundesliga/borussia-dortmund/67890/">Borussia Dortmund</a>
        """
        teams = parse_betano_standings_html(html, league="Bundesliga")

        self.assertEqual([team.name for team in teams], ["Bayern de Munique", "Borussia Dortmund"])
        self.assertEqual(teams[0].betano_team_id, "12345")

    def test_auto_approve_safe_match_and_review_ambiguous_match(self) -> None:
        approved, review = build_registry_matches(
            [
                BetanoTeam("Bundesliga", "Bayern de Munique", "1", ""),
                BetanoTeam("Bundesliga", "Real City", "2", ""),
            ],
            ["Bayern Munich", "Real City FC", "Real City B"],
        )

        self.assertEqual([row.betano_name for row in approved], ["Bayern de Munique"])
        self.assertEqual([row.betano_name for row in review], ["Real City"])

    def test_registry_alias_beats_fuzzy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_file = Path(tmp) / "registry.csv"
            approved, _ = build_registry_matches(
                [BetanoTeam("Bundesliga", "Bayern de Munique", "1", "")],
                ["Bayern Munich"],
            )
            write_registry_aliases(approved, registry_file)

            result = match_team_name(
                "Bayern de Munique",
                ["Bayern Munich"],
                {},
                league="Bundesliga",
                registry_file=registry_file,
            )

            self.assertEqual(result.match_status, "MATCH_REGISTRY_APPROVED")
            self.assertEqual(result.match_source, "team_registry")

    def test_fuzzy_remains_fuzzy_without_registry(self) -> None:
        result = match_team_name("Bayern Munich FC", ["Bayern Munich"], {}, registry_file=None)

        self.assertEqual(result.match_status, "auto_fuzzy_high")


if __name__ == "__main__":
    unittest.main()
