from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from vcbet.core.risk_policy import safety_gate_flags
from vcbet.service.team_registry_api import (
    approve_registry_alias,
    list_registry_leagues,
    load_approved_registry_aliases,
    load_pending_registry_reviews,
    reject_registry_alias,
    sync_registry_league,
)


class TeamRegistryApiTest(unittest.TestCase):
    def write_pending(self, root: Path) -> None:
        path = root / "data" / "team_registry" / "alias_review_pending.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "league",
                    "betano_name",
                    "betano_team_id",
                    "betano_url",
                    "suggested_footystats_name",
                    "top_score",
                    "review_reason",
                    "ambiguous_options",
                    "status",
                    "source",
                ],
                delimiter=";",
            )
            writer.writeheader()
            writer.writerow({
                "league": "Bundesliga",
                "betano_name": "Real City",
                "betano_team_id": "99",
                "betano_url": "https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/real-city/99-t/",
                "suggested_footystats_name": "Real City FC",
                "top_score": "0.9100",
                "review_reason": "low_score_gap",
                "ambiguous_options": "Real City FC:0.9100 | Real City B:0.8900",
                "status": "pending_review",
                "source": "sync_team_aliases",
            })

    def test_missing_pending_file_returns_empty_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_pending_registry_reviews(Path(tmp))

            self.assertEqual(payload["items"], [])
            self.assertEqual(payload["total"], 0)

    def test_approve_pending_alias_adds_registry_and_resolves_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_pending(root)

            result = approve_registry_alias(root, {
                "league": "Bundesliga",
                "betano_name": "Real City",
                "betano_team_id": "99",
                "footystats_name": "Real City FC",
            })
            approved = load_approved_registry_aliases(root)
            pending = load_pending_registry_reviews(root)

            self.assertEqual(result["added"], 1)
            self.assertEqual(approved["total"], 1)
            self.assertEqual(approved["items"][0]["match_status"], "MATCH_REGISTRY_APPROVED")
            self.assertEqual(approved["items"][0]["source"], "ui_review")
            self.assertEqual(pending["total"], 0)

    def test_approve_does_not_duplicate_same_team_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_pending(root)

            payload = {
                "league": "Bundesliga",
                "betano_name": "Real City",
                "betano_team_id": "99",
                "footystats_name": "Real City FC",
            }
            approve_registry_alias(root, payload)
            result = approve_registry_alias(root, payload)
            approved = load_approved_registry_aliases(root)

            self.assertEqual(result["added"], 0)
            self.assertEqual(approved["total"], 1)

    def test_reject_pending_alias_preserves_audit_without_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_pending(root)

            result = reject_registry_alias(root, {
                "league": "Bundesliga",
                "betano_name": "Real City",
                "betano_team_id": "99",
            })
            approved = load_approved_registry_aliases(root)
            rejected_file = root / "data" / "team_registry" / "alias_review_rejected.csv"

            self.assertEqual(result["rejected"], 1)
            self.assertEqual(approved["total"], 0)
            self.assertTrue(rejected_file.exists())

    def test_list_registry_leagues_returns_syncable_configured_leagues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = list_registry_leagues(Path(tmp))

            self.assertTrue(payload["items"])
            self.assertIn("name", payload["items"][0])

    def test_sync_registry_league_from_fixture_html_writes_review_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xg_dir = root / "data" / "runs" / "2026-04-25" / "fixture"
            xg_dir.mkdir(parents=True)
            (xg_dir / "xg_snapshot.csv").write_text(
                "league;team_name;xg;xga\nBundesliga;Real City FC;1.2;1.1\nBundesliga;Real City B;1.0;1.3\n",
                encoding="utf-8",
            )
            html = root / "betano.html"
            html.write_text(
                """
                <tr data-qa="standings_team_0">
                  <td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/real-city/99-t/">Real City</a></td>
                </tr>
                """,
                encoding="utf-8",
            )

            result = sync_registry_league(root, {"league": "Bundesliga", "source": "saved_html", "html_path": str(html)})
            pending = load_pending_registry_reviews(root)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["betano_total"], 1)
            self.assertEqual(result["review_count"], 1)
            self.assertEqual(pending["total"], 1)

    def test_invalid_page_text_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data" / "team_registry" / "alias_review_pending.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "league;betano_name;betano_team_id;betano_url;suggested_footystats_name;top_score;review_reason;ambiguous_options;status;source\n"
                "Bundesliga;odds atualizadas da Bundesliga e aposte;216;https://www.betano.bet.br/sport/futebol/alemanha/bundesliga/216/;FC St. Pauli;0.9000;below_threshold;;pending_review;sync_team_aliases\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                approve_registry_alias(root, {
                    "league": "Bundesliga",
                    "betano_name": "odds atualizadas da Bundesliga e aposte",
                    "betano_team_id": "216",
                    "footystats_name": "FC St. Pauli",
                })

    def test_invalid_betano_league_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data" / "team_registry" / "alias_review_pending.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "league;betano_name;betano_team_id;betano_url;suggested_footystats_name;top_score;review_reason;ambiguous_options;status;source\n"
                "Bundesliga;Mainz 05;216;https://www.betano.bet.br/sport/futebol/alemanha/bundesliga/216/;1. FSV Mainz 05;0.9900;;;pending_review;sync_team_aliases\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                approve_registry_alias(root, {
                    "league": "Bundesliga",
                    "betano_name": "Mainz 05",
                    "betano_team_id": "216",
                    "footystats_name": "1. FSV Mainz 05",
                })

    def test_low_score_approval_requires_manual_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_pending(root)

            with self.assertRaises(ValueError):
                approve_registry_alias(root, {
                    "league": "Bundesliga",
                    "betano_name": "Real City",
                    "betano_team_id": "99",
                    "footystats_name": "Real City FC",
                    "top_score": "0.6000",
                })

            result = approve_registry_alias(root, {
                "league": "Bundesliga",
                "betano_name": "Real City",
                "betano_team_id": "99",
                "footystats_name": "Real City FC",
                "top_score": "0.6000",
                "manual_override": True,
                "manual_override_reason": "validado manualmente contra standings",
            })
            self.assertEqual(result["added"], 1)

    def test_partial_live_coverage_blocks_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xg_dir = root / "data" / "runs" / "2026-04-25" / "fixture"
            xg_dir.mkdir(parents=True)
            teams = "\n".join(f"Bundesliga;Footy {idx};1.0;1.0" for idx in range(18))
            (xg_dir / "xg_snapshot.csv").write_text(f"league;team_name;xg;xga\n{teams}\n", encoding="utf-8")
            html = root / "partial.html"
            html.write_text("\n".join(
                f'<tr data-qa="standings_team_{idx}"><td><a href="https://www.betano.bet.br/sport/futebol/competicoes/alemanha/216/team-{idx}/{1000 + idx}-t/">Team {idx}</a></td></tr>'
                for idx in range(5)
            ), encoding="utf-8")

            result = sync_registry_league(root, {"league": "Bundesliga", "source": "saved_html", "html_path": str(html)})

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["coverage_status"], "failed_partial_coverage")
            self.assertFalse((root / "configs" / "team_registry" / "betano_footystats_aliases.csv").exists())

    def test_sync_all_continues_after_failed_league(self) -> None:
        from vcbet.service import team_registry_api

        original = team_registry_api.sync_registry_league
        calls = {"count": 0}

        def fake_sync(project_root: Path, payload: dict[str, object]) -> dict[str, object]:
            calls["count"] += 1
            if calls["count"] == 1:
                return {"league": payload["league"], "status": "blocked", "coverage_status": "failed_partial_coverage"}
            return {"league": payload["league"], "status": "ok", "coverage_status": "ok"}

        team_registry_api.sync_registry_league = fake_sync
        try:
            result = team_registry_api.sync_all_registry_leagues(Path(tempfile.gettempdir()))
        finally:
            team_registry_api.sync_registry_league = original

        self.assertGreaterEqual(result["total"], 2)
        self.assertEqual(result["status"], "partial")

    def test_match_fuzzy_remains_blocked(self) -> None:
        self.assertIn("MATCH_FUZZY", safety_gate_flags(["MATCH_FUZZY"]))


if __name__ == "__main__":
    unittest.main()
