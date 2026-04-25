from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vcbet.core.team_matcher import match_team_name
from vcbet.core.team_registry import (
    BetanoTeam,
    build_registry_matches,
    normalize_team_name,
    parse_betano_phase_standings_json,
    parse_betano_standings_html,
    parse_betano_standings_html_with_diagnostics,
    write_registry_aliases,
)
from scripts.sync_team_aliases import coverage_diagnostics, extract_phase_params


def phase_payload(names: list[str]) -> dict:
    return {
        "data": {
            "id": 4935355,
            "title": "Bundesliga 2025/26",
            "groups": [{
                "teams": [
                    {
                        "information": {"name": name, "teamId": str(100000 + idx), "rank": idx + 1},
                        "teamPageUrl": f"/sport/futebol/competicoes/alemanha/216/{normalize_team_name(name).replace(' ', '-')}/{100000 + idx}-t/",
                    }
                    for idx, name in enumerate(names)
                ]
            }],
        }
    }


class TeamRegistryTest(unittest.TestCase):
    def test_normalization_handles_translations_and_suffixes(self) -> None:
        self.assertEqual(normalize_team_name("Bayern de Munique FC"), "bayern munich")
        self.assertEqual(normalize_team_name("1. FC Köln"), "1 cologne")

    def test_parse_betano_standings_html_extracts_team_names_and_ids(self) -> None:
        html = """
        <tr data-qa="standings_team_0">
          <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/bayern-de-munique/12345-t/">Bayern de Munique</a></td>
        </tr>
        <tr data-qa="standings_team_1">
          <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/borussia-dortmund/67890-t/">Borussia Dortmund</a></td>
        </tr>
        """
        teams = parse_betano_standings_html(html, league="Bundesliga")

        self.assertEqual([team.name for team in teams], ["Bayern de Munique", "Borussia Dortmund"])
        self.assertEqual(teams[0].betano_team_id, "12345")

    def test_parse_betano_standings_html_ignores_non_standings_team_links(self) -> None:
        html = """
        <aside>
          <a href="/sport/futebol/alemanha/bundesliga/bayern-de-munique/12345/">Bayern de Munique</a>
          <a href="/sport/futebol/inglaterra/premier-league/arsenal/999/">Arsenal</a>
        </aside>
        <table>
          <tbody>
            <tr data-qa="standings_team_0">
              <td>1</td>
              <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/bayern-de-munique/108215-t/"><span>Bayern de Munique</span></a></td>
            </tr>
            <tr data-qa="standings_team_1">
              <td>2</td>
              <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/borussia-dortmund/108216-t/"><span>Borussia Dortmund</span></a></td>
            </tr>
          </tbody>
        </table>
        <section>
          <a href="/sport/futebol/alemanha/bundesliga/rb-leipzig/777/">RB Leipzig</a>
        </section>
        """

        teams = parse_betano_standings_html(html, league="Bundesliga")

        self.assertEqual([team.name for team in teams], ["Bayern de Munique", "Borussia Dortmund"])
        self.assertEqual([team.betano_team_id for team in teams], ["108215", "108216"])

    def test_parse_betano_standings_html_preserves_mainz_05_row(self) -> None:
        html = """
        <tr data-qa="standings_team_9">
          <td><div data-qa="last_results"><a href="/sport/futebol/alemanha/bundesliga/noise/111/">Ruido</a></div></td>
          <td>
            <a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/mainz-05/106861-t/">
              <img alt="">
              <span>Mainz 05</span>
              <div data-qa="event-selection"></div>
            </a>
          </td>
        </tr>
        """

        teams = parse_betano_standings_html(html, league="Bundesliga")

        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0].name, "Mainz 05")
        self.assertEqual(teams[0].betano_team_id, "106861")

    def test_phase_standings_json_preserves_numbered_team_names(self) -> None:
        names = [
            "1. FC Heidenheim 1846", "1. FC Köln", "1. FSV Mainz 05", "FC Bayern München",
            "Bayer 04 Leverkusen", "BVB 09 Borussia Dortmund", "FC St. Pauli", "Hamburger SV",
            "Rasen Ballsport Leipzig", "SC Freiburg", "VfB Stuttgart 1893", "VfL Wolfsburg",
            "SV Werder Bremen", "TSG 1899 Hoffenheim", "Eintracht Frankfurt", "FC Augsburg",
            "Borussia VfL Mönchengladbach", "1. FC Union Berlin",
        ]

        parsed = parse_betano_phase_standings_json(phase_payload(names), league="Bundesliga", source_url="https://api.test")

        self.assertEqual(len(parsed.teams), 18)
        self.assertIn("1. FSV Mainz 05", [team.name for team in parsed.teams])
        self.assertIn("1. FC Köln", [team.name for team in parsed.teams])
        self.assertEqual(parsed.phase_id, "4935355")

    def test_extract_phase_standings_params(self) -> None:
        params = extract_phase_params("https://www.betano.bet.br/api/league/phaseStandings/?sportId=1&leagueId=216&gLeagueIds=216&phaseId=4935355")

        self.assertEqual(params["leagueId"], "216")
        self.assertEqual(params["phaseId"], "4935355")

    def test_parse_real_bundesliga_fixture_extracts_18_standings_rows_when_available(self) -> None:
        fixture = Path("dev_asset/betano_classificacao.htm")
        if not fixture.exists():
            self.skipTest("dev_asset/betano_classificacao.htm indisponível")

        teams = parse_betano_standings_html(fixture.read_text(encoding="utf-8", errors="replace"), league="Bundesliga")

        self.assertEqual(len(teams), 18)
        self.assertIn("Mainz 05", [team.name for team in teams])

    def test_coverage_diagnostics_reports_unmatched_and_deduped_entries(self) -> None:
        html = """
        <tr data-qa="standings_team_0">
          <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/bayern-de-munique/108215-t/">Bayern de Munique</a></td>
        </tr>
        <tr data-qa="standings_team_0">
          <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/bayern-de-munique/108215-t/">Bayern de Munique</a></td>
        </tr>
        <tr data-qa="standings_team_1">
          <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/rb-leipzig/108344-t/">RB Leipzig</a></td>
        </tr>
        """
        parsed = parse_betano_standings_html_with_diagnostics(html, league="Bundesliga")
        approved, review = build_registry_matches(parsed.teams, ["FC Bayern München", "Hamburger SV"])

        diagnostics = coverage_diagnostics(parsed.teams, ["FC Bayern München", "Hamburger SV"], approved, review)

        self.assertEqual(parsed.raw_count, 3)
        self.assertEqual(parsed.duplicate_count, 1)
        self.assertEqual(diagnostics["total_betano"], 2)
        self.assertEqual(diagnostics["total_footystats"], 2)
        self.assertEqual(diagnostics["auto_count"], 1)
        self.assertEqual(diagnostics["review_count"], 1)
        self.assertEqual(diagnostics["footystats_without_betano_candidate"], ["Hamburger SV"])

    def test_auto_approve_safe_match_and_review_ambiguous_match(self) -> None:
        approved, review = build_registry_matches(
            [
                BetanoTeam("Bundesliga", "Bayern de Munique", "1", "https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/bayern-de-munique/1-t/"),
                BetanoTeam("Bundesliga", "Real City", "2", "https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/real-city/2-t/"),
            ],
            ["Bayern Munich", "Real City FC", "Real City B"],
        )

        self.assertEqual([row.betano_name for row in approved], ["Bayern de Munique", "Real City"])
        self.assertEqual([row.betano_name for row in review], [])

    def test_registry_alias_beats_fuzzy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_file = Path(tmp) / "registry.csv"
            approved, _ = build_registry_matches(
                [BetanoTeam("Bundesliga", "Bayern de Munique", "1", "https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/bayern-de-munique/1-t/")],
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
