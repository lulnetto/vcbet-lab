from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.collectors.results_collector import (
    MatchTarget,
    build_candidate_from_event,
    match_result_for_target,
    slug_text,
)
from vcbet.settlement.settlement_engine import (
    apply_results_file,
    resolve_final_fields,
    validate_no_non_final_settlements,
)


class ResultsCollectorSettlementHardeningTests(unittest.TestCase):
    def _alias_map(self, league: str, *pairs: tuple[str, str]) -> dict[tuple[str, str], str]:
        return {(slug_text(league), slug_text(ledger_name)): sofascore_name for ledger_name, sofascore_name in pairs}

    def test_inprogress_event_does_not_export_liquidable_goals(self) -> None:
        event = {
            "id": 123,
            "homeTeam": {"name": "Frankfurt"},
            "awayTeam": {"name": "Hamburgo"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0},
            "status": {"type": "inprogress", "description": "1st half"},
        }

        result = build_candidate_from_event("Liga", event, "https://example.test", "sofascore_api")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.bet_status, "open")
        self.assertIsNone(result.home_goals)
        self.assertIsNone(result.away_goals)
        self.assertEqual(result.settlement_confidence, "medium")

    def test_unknown_status_with_score_stays_open(self) -> None:
        event = {
            "id": 456,
            "homeTeam": {"name": "Newcastle"},
            "awayTeam": {"name": "Brighton"},
            "homeScore": {"current": 2},
            "awayScore": {"current": 0},
            "status": {"type": "live", "description": "unknown"},
        }

        result = build_candidate_from_event("Liga", event, "https://example.test", "sofascore_api")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.bet_status, "open")
        self.assertIsNone(result.home_goals)
        self.assertIsNone(result.away_goals)
        self.assertEqual(result.settlement_confidence, "low")

    def test_sofascore_alias_resolves_finished_match(self) -> None:
        target = MatchTarget(
            league="Segunda División",
            match_name="Racing Santander - Huesca",
            home_team="Racing Santander",
            away_team="Huesca",
            match_datetime=None,
        )
        event = {
            "id": 789,
            "homeTeam": {"name": "Real Racing Club"},
            "awayTeam": {"name": "Huesca"},
            "homeScore": {"current": 4},
            "awayScore": {"current": 2},
            "status": {"type": "finished", "description": "Ended"},
        }
        candidate = build_candidate_from_event("Segunda División", event, "https://example.test", "sofascore_api")
        assert candidate is not None

        matched = match_result_for_target(
            target,
            [candidate],
            aliases=self._alias_map("Segunda División", ("Racing Santander", "Real Racing Club")),
        )

        self.assertIsNotNone(matched)
        assert matched is not None
        self.assertEqual(matched.bet_status, "settled")
        self.assertEqual(matched.settlement_confidence, "high")
        self.assertEqual(matched.home_goals, 4)
        self.assertEqual(matched.away_goals, 2)
        self.assertIn("sofascore_result_alias", matched.matched_via or "")

    def test_sofascore_alias_resolves_inprogress_match_as_open(self) -> None:
        target = MatchTarget(
            league="Ligue 1",
            match_name="Lyon - Rennes",
            home_team="Lyon",
            away_team="Rennes",
            match_datetime=None,
        )
        event = {
            "id": 456,
            "homeTeam": {"name": "Olympique Lyonnais"},
            "awayTeam": {"name": "Stade Rennais"},
            "homeScore": {"current": 1},
            "awayScore": {"current": 1},
            "status": {"type": "inprogress", "description": "2nd half"},
        }
        candidate = build_candidate_from_event("Ligue 1", event, "https://example.test", "sofascore_api")
        assert candidate is not None

        matched = match_result_for_target(
            target,
            [candidate],
            aliases=self._alias_map(
                "Ligue 1",
                ("Lyon", "Olympique Lyonnais"),
                ("Rennes", "Stade Rennais"),
            ),
        )

        self.assertIsNotNone(matched)
        assert matched is not None
        self.assertEqual(matched.bet_status, "open")
        self.assertEqual(matched.settlement_confidence, "high")
        self.assertEqual(matched.settlement_note, "evento encontrado no Sofascore, mas ainda não finalizado")
        self.assertEqual(matched.source_event_id, "456")
        self.assertIsNone(matched.home_goals)
        self.assertIsNone(matched.away_goals)
        self.assertIn("sofascore_result_alias", matched.matched_via or "")

    def test_without_alias_rejects_low_team_score_match(self) -> None:
        target = MatchTarget(
            league="Segunda División",
            match_name="Racing Santander - Huesca",
            home_team="Racing Santander",
            away_team="Huesca",
            match_datetime=None,
        )
        event = {
            "id": 789,
            "homeTeam": {"name": "Real Racing Club"},
            "awayTeam": {"name": "Huesca"},
            "homeScore": {"current": 4},
            "awayScore": {"current": 2},
            "status": {"type": "finished", "description": "Ended"},
        }
        candidate = build_candidate_from_event("Segunda División", event, "https://example.test", "sofascore_api")
        assert candidate is not None

        self.assertIsNone(match_result_for_target(target, [candidate], aliases={}))


class SettlementEngineHardeningTests(unittest.TestCase):
    def _ledger_row(self) -> dict:
        return {
            "bet_id": "bet-1",
            "league": "Liga",
            "match_datetime": "2026-05-02 10:30",
            "home_team": "Frankfurt",
            "away_team": "Hamburgo",
            "match_name": "Frankfurt - Hamburgo",
            "market_type": "total_goals",
            "side": "under",
            "line": 2.5,
            "target_team_role": "geral",
            "odd_entrada": 1.9,
            "stake_units": 1.0,
            "bet_executed": "no",
            "auto_bet_status": "open",
            "auto_settlement_status": "pending",
            "final_bet_status": "open",
            "final_settlement_status": "pending",
            "settled_at": pd.NA,
            "result_units_model": pd.NA,
            "result_units_real": pd.NA,
        }

    def _apply_result_row(self, result_row: dict) -> pd.DataFrame:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            pd.DataFrame([result_row]).to_csv(path, index=False, sep=";")
            ledger = pd.DataFrame([self._ledger_row()])
            return resolve_final_fields(apply_results_file(ledger, path))

    def test_open_auto_result_never_settles_even_with_score_columns(self) -> None:
        updated = self._apply_result_row(
            {
                "league": "Liga",
                "match_name": "Frankfurt - Hamburgo",
                "home_team": "Frankfurt",
                "away_team": "Hamburgo",
                "match_datetime": "2026-05-02 10:30",
                "home_goals": 0,
                "away_goals": 0,
                "bet_status": "open",
                "settlement_confidence": "medium",
                "settlement_note": "partida ainda n\u00e3o finalizada",
                "status_raw": "inprogress|1st half",
            }
        )

        row = updated.iloc[0]
        self.assertEqual(row["final_bet_status"], "open")
        self.assertEqual(row["final_settlement_status"], "pending")
        self.assertTrue(pd.isna(row["final_home_goals"]))
        self.assertTrue(pd.isna(row["final_away_goals"]))
        self.assertTrue(pd.isna(row["settled_at"]))
        self.assertTrue(pd.isna(row["result_units_model"]))

    def test_terminal_high_confidence_auto_result_can_settle(self) -> None:
        updated = self._apply_result_row(
            {
                "league": "Liga",
                "match_name": "Frankfurt - Hamburgo",
                "home_team": "Frankfurt",
                "away_team": "Hamburgo",
                "match_datetime": "2026-05-02 10:30",
                "home_goals": 1,
                "away_goals": 0,
                "bet_status": "settled",
                "settlement_confidence": "high",
                "settlement_note": "placar final coletado automaticamente via Sofascore",
                "status_raw": "finished|Ended",
            }
        )

        row = updated.iloc[0]
        self.assertEqual(row["final_bet_status"], "settled")
        self.assertEqual(row["final_settlement_status"], "win")
        self.assertEqual(row["final_home_goals"], 1)
        self.assertEqual(row["final_away_goals"], 0)
        self.assertFalse(pd.isna(row["settled_at"]))
        self.assertEqual(row["result_units_model"], 0.9)

    def test_results_file_bet_id_restricts_matching_when_present(self) -> None:
        updated = self._apply_result_row(
            {
                "bet_id": "other-bet",
                "league": "Liga",
                "match_name": "Frankfurt - Hamburgo",
                "home_team": "Frankfurt",
                "away_team": "Hamburgo",
                "match_datetime": "2026-05-02 10:30",
                "home_goals": 1,
                "away_goals": 0,
                "bet_status": "settled",
                "settlement_confidence": "high",
                "settlement_note": "placar final coletado automaticamente via Sofascore",
                "status_raw": "finished|Ended",
            }
        )

        row = updated.iloc[0]
        self.assertEqual(row["final_bet_status"], "open")
        self.assertEqual(row["final_settlement_status"], "pending")
        self.assertTrue(pd.isna(row["result_units_model"]))

    def test_open_high_confidence_result_with_bet_id_marks_match_resolved_without_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            pd.DataFrame(
                [
                    {
                        "bet_id": "bet-1",
                        "league": "Liga",
                        "match_name": "Frankfurt - Hamburgo",
                        "home_team": "Frankfurt",
                        "away_team": "Hamburgo",
                        "match_datetime": "2026-05-02 10:30",
                        "home_goals": pd.NA,
                        "away_goals": pd.NA,
                        "bet_status": "open",
                        "settlement_confidence": "high",
                        "settlement_source": "sofascore_api",
                        "settlement_note": "evento encontrado no Sofascore, mas ainda não finalizado",
                        "status_raw": "inprogress|2nd half",
                        "source_event_id": "456",
                        "source_url": "https://example.test/events/last/0",
                    }
                ]
            ).to_csv(path, index=False, sep=";")
            ledger = pd.DataFrame(
                [
                    {
                        **self._ledger_row(),
                        "final_bet_status": "unmatched",
                        "final_settlement_status": "unmatched",
                    }
                ]
            )

            updated = resolve_final_fields(apply_results_file(ledger, path))

        row = updated.iloc[0]
        self.assertEqual(row["auto_bet_status"], "open")
        self.assertEqual(row["auto_settlement_status"], "pending")
        self.assertEqual(row["final_bet_status"], "open")
        self.assertEqual(row["final_settlement_status"], "pending")
        self.assertEqual(row["sofascore_event_id"], "456")
        self.assertEqual(row["match_resolution_status"], "resolved")
        self.assertTrue(pd.isna(row["match_resolution_reason"]))
        self.assertEqual(row["resolved_result_provider"], "sofascore_api")
        self.assertEqual(row["resolved_event_id"], "456")
        self.assertTrue(pd.isna(row["result_units_model"]))

    def test_legacy_settled_rows_without_status_raw_are_preserved(self) -> None:
        ledger = pd.DataFrame(
            [
                {
                    **self._ledger_row(),
                    "auto_bet_status": "settled",
                    "auto_settlement_status": "pending",
                    "final_home_goals": 1,
                    "final_away_goals": 0,
                    "final_bet_status": "settled",
                    "final_settlement_status": "win",
                    "settlement_confidence": "high",
                    "settlement_note": "placar final coletado automaticamente via Sofascore",
                    "settled_at": "2026-05-02 12:00:00",
                }
            ]
        )

        updated = resolve_final_fields(ledger)

        row = updated.iloc[0]
        self.assertEqual(row["final_bet_status"], "settled")
        self.assertEqual(row["final_settlement_status"], "win")
        self.assertEqual(row["final_home_goals"], 1)
        self.assertEqual(row["final_away_goals"], 0)
        self.assertEqual(row["settled_at"], "2026-05-02 12:00:00")

    def test_ledger_validation_refuses_settled_open_auto_result(self) -> None:
        ledger = pd.DataFrame(
            [
                {
                    "bet_id": "bad-1",
                    "final_bet_status": "settled",
                    "auto_bet_status": "open",
                    "settlement_note": "partida ainda n\u00e3o finalizada",
                }
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "Refusing to settle non-final match result"):
            validate_no_non_final_settlements(ledger)


if __name__ == "__main__":
    unittest.main()
