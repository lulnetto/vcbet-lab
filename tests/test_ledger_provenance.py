from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.core.ledger_manager import append_new_picks_to_ledger, load_ledger
from vcbet.service.dashboard import build_dashboard_payload
from vcbet.settlement.settlement_engine import settle_ledger

try:
    from vcbet.service.api import _compact_pick_row
except ModuleNotFoundError:
    _compact_pick_row = None


def official_pick(**overrides) -> dict:
    payload = {
        "bet_id": "bet_phase3_001",
        "run_id": "run_phase3",
        "generated_at": "2026-04-24 12:00:00",
        "decision_timestamp": "2026-04-24 12:00:00",
        "league": "Liga Teste",
        "match_datetime": "2026-04-24 15:00",
        "home_team": "Casa FC",
        "away_team": "Fora FC",
        "match_name": "Casa FC - Fora FC",
        "market_type": "total_goals",
        "market_scope": "full_time",
        "market_raw": "Total de Gols Mais/Menos",
        "event_url": "https://example.test/match",
        "selection_raw": "Mais de 2.5",
        "line": 2.5,
        "side": "over",
        "target_team_role": "geral",
        "target_team_name": "geral",
        "odd_entrada": 2.2,
        "odd_justa": 1.75,
        "prob_model": 0.57,
        "ev_percent": 20.0,
        "confidence_score": 5,
        "stake_units": 1.0,
        "entry_reason": "EDGE_FORTE",
        "risk_flags": "SEM_FLAG",
        "pick_safety_status": "safe",
        "candidate_stage": "official_accepted_pick",
        "safety_gate_reason": "",
        "config_name": "champion_strict",
        "config_fingerprint": "abc123def456",
        "config_source_path": "configs/champion_strict.json",
        "config_snapshot_file": "data/runs/2026-04-24/run_phase3/strategy_config_snapshot.json",
        "source_run_id": "run_phase3",
        "source_snapshot_ref": "odds:data/runs/odds_snapshot.csv|xg:data/runs/xg_snapshot.csv",
        "odds_source_run_id": "odds_run_phase3",
        "xg_source_run_id": "xg_run_phase3",
        "odds_snapshot_file": "data/runs/odds_snapshot.csv",
        "xg_snapshot_file": "data/runs/xg_snapshot.csv",
        "odds_snapshot_hash": "oddsmd5",
        "xg_snapshot_hash": "xgmd5",
        "signal_version": "ev_pipeline_v1",
        "pipeline_version": "pipeline_ev_phase3_provenance",
    }
    payload.update(overrides)
    return payload


class LedgerProvenanceTest(unittest.TestCase):
    def test_new_official_picks_persist_provenance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "bets_ledger.csv"

            append_new_picks_to_ledger(pd.DataFrame([official_pick()]), ledger_file)
            ledger = load_ledger(ledger_file)
            row = ledger.iloc[0]

            self.assertEqual(row["run_id"], "run_phase3")
            self.assertEqual(row["config_name"], "champion_strict")
            self.assertEqual(row["config_fingerprint"], "abc123def456")
            self.assertEqual(row["source_run_id"], "run_phase3")
            self.assertEqual(row["odds_source_run_id"], "odds_run_phase3")
            self.assertEqual(row["xg_source_run_id"], "xg_run_phase3")
            self.assertEqual(row["odds_snapshot_hash"], "oddsmd5")
            self.assertEqual(row["xg_snapshot_hash"], "xgmd5")
            self.assertEqual(row["decision_timestamp"], "2026-04-24 12:00:00")
            self.assertEqual(row["pick_safety_status"], "safe")
            self.assertEqual(row["candidate_stage"], "official_accepted_pick")
            self.assertTrue(pd.isna(row["safety_gate_reason"]) or row["safety_gate_reason"] == "")

    def test_old_ledger_rows_without_new_columns_load_and_settle_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "old_ledger.csv"
            legacy = pd.DataFrame([
                {
                    "bet_id": "legacy_001",
                    "run_id": "old_run",
                    "created_at": "2026-04-23 12:00:00",
                    "league": "Liga Teste",
                    "match_datetime": "2026-04-24 15:00",
                    "home_team": "Casa FC",
                    "away_team": "Fora FC",
                    "match_name": "Casa FC - Fora FC",
                    "market_type": "total_goals",
                    "market_scope": "full_time",
                    "target_team_role": "geral",
                    "target_team_name": "geral",
                    "side": "over",
                    "line": 2.5,
                    "selection_raw": "Mais de 2.5",
                    "odd_entrada": 2.0,
                    "stake_units": 0.5,
                    "final_bet_status": "open",
                    "final_settlement_status": "pending",
                }
            ])
            legacy.to_csv(ledger_file, index=False, sep=";", encoding="utf-8-sig")

            loaded = load_ledger(ledger_file)
            self.assertIn("config_name", loaded.columns)
            self.assertIn("decision_timestamp", loaded.columns)
            self.assertTrue(pd.isna(loaded.loc[0, "config_name"]))

            payload = build_dashboard_payload(loaded)
            self.assertEqual(payload["summary"]["total_entries"], 1)

            settled_path, settled_count = settle_ledger(ledger_file=ledger_file, overrides_file=None)
            self.assertEqual(settled_path, ledger_file)
            self.assertEqual(settled_count, 0)

    def test_legacy_pick_export_without_new_fields_still_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "bets_ledger.csv"
            legacy_pick = official_pick(
                bet_id="legacy_export_001",
                config_name=pd.NA,
                config_fingerprint=pd.NA,
                source_run_id=pd.NA,
                odds_snapshot_hash=pd.NA,
                xg_snapshot_hash=pd.NA,
                decision_timestamp=pd.NA,
            )
            for field in [
                "config_name",
                "config_fingerprint",
                "source_run_id",
                "odds_snapshot_hash",
                "xg_snapshot_hash",
                "decision_timestamp",
            ]:
                legacy_pick.pop(field, None)

            append_new_picks_to_ledger(pd.DataFrame([legacy_pick]), ledger_file)
            ledger = load_ledger(ledger_file)

            self.assertEqual(len(ledger), 1)
            self.assertIn("config_name", ledger.columns)
            self.assertEqual(ledger.loc[0, "created_at"], "2026-04-24 12:00:00")

            if _compact_pick_row is not None:
                compact = _compact_pick_row(ledger.fillna("").iloc[0].astype(str).to_dict())
                self.assertEqual(compact["run_id"], "run_phase3")
                self.assertEqual(compact["decision_timestamp"], "2026-04-24 12:00:00")


if __name__ == "__main__":
    unittest.main()
