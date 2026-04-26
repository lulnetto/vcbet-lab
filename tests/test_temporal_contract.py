from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.core.ledger_manager import append_new_picks_to_ledger, load_ledger
from vcbet.core.pipeline_ev import processar_pipeline
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION, snapshot_time_from_dataframe
from vcbet.replay.replay_pipeline import _resolve_source_run
from vcbet.service.dashboard import build_dashboard_payload


def write_strategy_config(path: Path, *, max_snapshot_age_hours: float) -> Path:
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "test_temporal_config",
                    "label": "Test Temporal Config",
                },
                "data_quality": {
                    "max_snapshot_age_hours": max_snapshot_age_hours,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def write_pipeline_snapshots(root: Path, *, odds_collected_at: str | None, xg_collected_at: str | None) -> tuple[Path, Path]:
    source_dir = root / "2026-04-24" / "source_run"
    source_dir.mkdir(parents=True)
    odds_file = source_dir / "odds_snapshot.csv"
    xg_file = source_dir / "xg_snapshot.csv"

    odds_row = {
        "run_id": "source_run",
        "league": "Liga Teste",
        "match_datetime": "2026-04-24 15:00",
        "home_team": "Casa FC",
        "away_team": "Fora FC",
        "match_name": "Casa FC - Fora FC",
        "market_raw": "Total de Gols Mais/Menos",
        "selection_raw": "Mais de 2.5",
        "odd": 1.8,
        "event_url": "https://example.test/match",
        "market_type": "total_goals",
        "market_scope": "full_time",
        "side": "over",
        "line": 2.5,
        "target_team_role": "geral",
        "target_team_name": "geral",
        "normalized_status": "ok",
    }
    if odds_collected_at is not None:
        odds_row["collected_at"] = odds_collected_at
    pd.DataFrame([odds_row]).to_csv(odds_file, index=False, sep=";", encoding="utf-8-sig")

    xg_rows = [
        {
            "run_id": "source_run",
            "source": "footystats",
            "league": "Liga Teste",
            "team_name": "Casa FC",
            "xg": 1.5,
            "xga": 1.1,
            "xg_home": 1.5,
            "xg_away": 1.5,
            "xga_home": 1.1,
            "xga_away": 1.1,
        },
        {
            "run_id": "source_run",
            "source": "footystats",
            "league": "Liga Teste",
            "team_name": "Fora FC",
            "xg": 1.0,
            "xga": 1.4,
            "xg_home": 1.0,
            "xg_away": 1.0,
            "xga_home": 1.4,
            "xga_away": 1.4,
        },
    ]
    if xg_collected_at is not None:
        for row in xg_rows:
            row["collected_at"] = xg_collected_at
    pd.DataFrame(xg_rows).to_csv(xg_file, index=False, sep=";", encoding="utf-8-sig")
    return odds_file, xg_file


class TemporalContractTest(unittest.TestCase):
    def test_snapshot_time_uses_latest_collected_at(self) -> None:
        df = pd.DataFrame(
            {
                "collected_at": [
                    "2026-04-24 10:00:00",
                    "2026-04-24 10:05:00",
                ]
            }
        )

        self.assertEqual(snapshot_time_from_dataframe(df), "2026-04-24 10:05:00")

    def test_pipeline_persists_temporal_contract_in_report_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "2026-04-24" / "source_run"
            source_dir.mkdir(parents=True)
            odds_file = source_dir / "odds_snapshot.csv"
            xg_file = source_dir / "xg_snapshot.csv"
            output_dir = root / "runs"
            alias_file = root / "aliases.json"
            alias_file.write_text("{}", encoding="utf-8")
            config_file = write_strategy_config(root / "strategy.json", max_snapshot_age_hours=100000)

            pd.DataFrame(
                [
                    {
                        "run_id": "source_run",
                        "collected_at": "2026-04-24 09:30:00",
                        "league": "Liga Teste",
                        "match_datetime": "2026-04-24 15:00",
                        "home_team": "Casa FC",
                        "away_team": "Fora FC",
                        "match_name": "Casa FC - Fora FC",
                        "market_raw": "Total de Gols Mais/Menos",
                        "selection_raw": "Mais de 2.5",
                        "odd": 1.8,
                        "event_url": "https://example.test/match",
                        "market_type": "total_goals",
                        "market_scope": "full_time",
                        "side": "over",
                        "line": 2.5,
                        "target_team_role": "geral",
                        "target_team_name": "geral",
                        "normalized_status": "ok",
                    }
                ]
            ).to_csv(odds_file, index=False, sep=";", encoding="utf-8-sig")

            pd.DataFrame(
                [
                    {
                        "run_id": "source_run",
                        "collected_at": "2026-04-24 08:45:00",
                        "source": "footystats",
                        "league": "Liga Teste",
                        "team_name": "Casa FC",
                        "xg": 1.5,
                        "xga": 1.1,
                        "xg_home": 1.5,
                        "xg_away": 1.5,
                        "xga_home": 1.1,
                        "xga_away": 1.1,
                    },
                    {
                        "run_id": "source_run",
                        "collected_at": "2026-04-24 08:45:00",
                        "source": "footystats",
                        "league": "Liga Teste",
                        "team_name": "Fora FC",
                        "xg": 1.0,
                        "xga": 1.4,
                        "xg_home": 1.0,
                        "xg_away": 1.0,
                        "xga_home": 1.4,
                        "xga_away": 1.4,
                    },
                ]
            ).to_csv(xg_file, index=False, sep=";", encoding="utf-8-sig")

            processar_pipeline(
                odds_file=str(odds_file),
                xg_file=str(xg_file),
                run_id="temporal_run",
                output_dir=str(output_dir),
                alias_file=str(alias_file),
                ledger_file=str(root / "ledger.csv"),
                modo_debug=True,
                config_file=str(config_file),
            )

            run_dir = output_dir / "2026-04-24" / "temporal_run"
            report = json.loads((run_dir / "quality_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(report["provenance"]["odds_snapshot_time"], "2026-04-24 09:30:00")
            self.assertEqual(report["provenance"]["xg_asof"], "2026-04-24 08:45:00")
            self.assertEqual(report["provenance"]["temporal_contract_status"], "complete")
            self.assertEqual(report["data_quality"]["snapshot_validation"]["status"], "valid")
            self.assertEqual(manifest["odds_snapshot_time"], "2026-04-24 09:30:00")
            self.assertEqual(manifest["xg_asof"], "2026-04-24 08:45:00")
            self.assertEqual(manifest["snapshot_validation_status"], "valid")

    def test_pipeline_rejects_stale_snapshots_before_pricing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            odds_file, xg_file = write_pipeline_snapshots(
                root,
                odds_collected_at="2026-04-20 09:30:00",
                xg_collected_at="2026-04-20 08:45:00",
            )
            output_dir = root / "runs"
            alias_file = root / "aliases.json"
            alias_file.write_text("{}", encoding="utf-8")
            config_file = write_strategy_config(root / "strategy.json", max_snapshot_age_hours=1)

            with self.assertRaisesRegex(ValueError, "SnapshotValidator rejected snapshots"):
                processar_pipeline(
                    odds_file=str(odds_file),
                    xg_file=str(xg_file),
                    run_id="stale_snapshot_run",
                    output_dir=str(output_dir),
                    alias_file=str(alias_file),
                    ledger_file=str(root / "ledger.csv"),
                    config_file=str(config_file),
                )

            run_dir = output_dir / "2026-04-24" / "stale_snapshot_run"
            report = json.loads((run_dir / "quality_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            error_codes = {item["code"] for item in report["data_quality"]["snapshot_validation"]["errors"]}

            self.assertEqual(report["quality_status"], "rejected")
            self.assertIn("odds_snapshot_stale", error_codes)
            self.assertIn("xg_snapshot_stale", error_codes)
            self.assertEqual(report["outputs"]["final_picks_total"], 0)
            self.assertEqual(manifest["status"], "pipeline_rejected_snapshot")
            self.assertFalse((run_dir / "raw_candidates.csv").exists())
            self.assertFalse((root / "ledger.csv").exists())

    def test_pipeline_rejects_missing_snapshot_metadata_before_pricing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fresh_time = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            odds_file, xg_file = write_pipeline_snapshots(
                root,
                odds_collected_at=None,
                xg_collected_at=fresh_time,
            )
            output_dir = root / "runs"
            alias_file = root / "aliases.json"
            alias_file.write_text("{}", encoding="utf-8")
            config_file = write_strategy_config(root / "strategy.json", max_snapshot_age_hours=100000)

            with self.assertRaisesRegex(ValueError, "SnapshotValidator rejected snapshots"):
                processar_pipeline(
                    odds_file=str(odds_file),
                    xg_file=str(xg_file),
                    run_id="missing_snapshot_run",
                    output_dir=str(output_dir),
                    alias_file=str(alias_file),
                    ledger_file=str(root / "ledger.csv"),
                    config_file=str(config_file),
                )

            run_dir = output_dir / "2026-04-24" / "missing_snapshot_run"
            report = json.loads((run_dir / "quality_report.json").read_text(encoding="utf-8"))
            error_codes = {item["code"] for item in report["data_quality"]["snapshot_validation"]["errors"]}

            self.assertEqual(report["quality_status"], "rejected")
            self.assertIn("odds_snapshot_time_missing", error_codes)
            self.assertEqual(report["outputs"]["final_picks_total"], 0)
            self.assertFalse((run_dir / "raw_candidates.csv").exists())

    def test_replay_prefers_frozen_local_snapshots_over_manifest_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "data" / "runs" / "2026-04-24" / "source_run"
            source_dir.mkdir(parents=True)
            local_odds = source_dir / "odds_snapshot.csv"
            local_xg = source_dir / "xg_snapshot.csv"
            mutable_odds = Path(tmp) / "mutable_odds.csv"
            mutable_xg = Path(tmp) / "mutable_xg.csv"
            local_odds.write_text("run_id;collected_at\nlocal;2026-04-24 10:00:00\n", encoding="utf-8")
            local_xg.write_text("run_id;collected_at\nlocal;2026-04-24 09:00:00\n", encoding="utf-8")
            mutable_odds.write_text("run_id;collected_at\nmutable;2026-04-24 11:00:00\n", encoding="utf-8")
            mutable_xg.write_text("run_id;collected_at\nmutable;2026-04-24 11:00:00\n", encoding="utf-8")
            (source_dir / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "source_run",
                        "target_date": "2026-04-24",
                        "odds_snapshot_file": str(mutable_odds),
                        "xg_snapshot_file": str(mutable_xg),
                    }
                ),
                encoding="utf-8",
            )

            resolved = _resolve_source_run(source_dir)

            self.assertEqual(resolved["odds_path"], local_odds)
            self.assertEqual(resolved["xg_path"], local_xg)
            self.assertEqual(resolved["replay_input_contract"]["odds_source_mode"], "frozen_run_local")
            self.assertEqual(resolved["replay_input_contract"]["xg_source_mode"], "frozen_run_local")
            self.assertEqual(resolved["replay_input_contract"]["odds_snapshot_time"], "2026-04-24 10:00:00")
            self.assertEqual(resolved["replay_input_contract"]["xg_asof"], "2026-04-24 09:00:00")
            self.assertEqual(resolved["replay_input_contract"]["source_strength"], "strong")
            self.assertEqual(resolved["replay_input_contract"]["replay_source_strength"], "strong_frozen_inputs")
            self.assertEqual(resolved["replay_input_contract"]["replay_quality_status"], "strong_frozen_inputs_trace_incomplete")
            self.assertEqual(resolved["replay_input_contract"]["frozen_components"], ["odds", "xg"])
            self.assertIn("missing_historical_trace_fields", resolved["replay_input_contract"]["replay_limitations"])

    def test_replay_manifest_fallback_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "source_run"
            source_dir.mkdir()
            manifest_odds = Path(tmp) / "manifest_odds.csv"
            manifest_xg = Path(tmp) / "manifest_xg.csv"
            manifest_odds.write_text("run_id;collected_at\nmanifest;2026-04-24 10:00:00\n", encoding="utf-8")
            manifest_xg.write_text("run_id;collected_at\nmanifest;2026-04-24 09:00:00\n", encoding="utf-8")
            (source_dir / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "source_run",
                        "target_date": "2026-04-24",
                        "odds_snapshot_file": str(manifest_odds),
                        "xg_snapshot_file": str(manifest_xg),
                    }
                ),
                encoding="utf-8",
            )

            resolved = _resolve_source_run(source_dir)

            self.assertEqual(resolved["odds_path"], manifest_odds)
            self.assertEqual(resolved["xg_path"], manifest_xg)
            self.assertEqual(resolved["replay_input_contract"]["odds_source_mode"], "manifest_reference")
            self.assertEqual(resolved["replay_input_contract"]["xg_source_mode"], "manifest_reference")
            self.assertEqual(resolved["replay_input_contract"]["odds_snapshot_time"], "2026-04-24 10:00:00")
            self.assertEqual(resolved["replay_input_contract"]["xg_asof"], "2026-04-24 09:00:00")
            self.assertEqual(resolved["replay_input_contract"]["source_strength"], "weak_fallback")
            self.assertEqual(resolved["replay_input_contract"]["replay_source_strength"], "partial_fallback_inputs")
            self.assertEqual(resolved["replay_input_contract"]["replay_quality_status"], "partial_fallback_trace_incomplete")
            self.assertEqual(resolved["replay_input_contract"]["fallback_components"], ["odds", "xg"])
            self.assertIn("uses_manifest_reference_fallback_inputs", resolved["replay_input_contract"]["replay_limitations"])

    def test_replay_quality_is_strong_when_frozen_inputs_and_trace_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "data" / "runs" / "2026-04-24" / "source_run"
            source_dir.mkdir(parents=True)
            (source_dir / "odds_snapshot.csv").write_text("run_id;collected_at\nlocal;2026-04-24 10:00:00\n", encoding="utf-8")
            (source_dir / "xg_snapshot.csv").write_text("run_id;collected_at\nlocal;2026-04-24 09:00:00\n", encoding="utf-8")
            (source_dir / "picks_snapshot.csv").write_text("run_id\nsource_run\n", encoding="utf-8")
            (source_dir / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "source_run",
                        "target_date": "2026-04-24",
                        "decision_timestamp": "2026-04-24 10:05:00",
                        "temporal_contract_status": "complete",
                        "config_name": "legacy_v2",
                        "config_fingerprint": "abc123",
                        "config_snapshot_file": str(source_dir / "config_snapshot.json"),
                        "signal_version": "signal_v1",
                        "pipeline_version": "pipeline_v1",
                    }
                ),
                encoding="utf-8",
            )

            resolved = _resolve_source_run(source_dir)
            contract = resolved["replay_input_contract"]

            self.assertEqual(contract["replay_quality_status"], "strong_frozen_traceable")
            self.assertEqual(contract["replay_source_strength"], "strong_frozen_inputs")
            self.assertEqual(contract["temporal_contract_status"], "complete")
            self.assertEqual(contract["missing_trace_fields"], [])
            self.assertEqual(contract["replay_limitations"], [])
            self.assertEqual(contract["component_source_modes"]["picks"], "frozen_run_local")
            self.assertEqual(contract["config_trace"]["config_fingerprint"], "abc123")
            self.assertEqual(contract["code_trace"]["pipeline_version"], "pipeline_v1")

    def test_legacy_replay_trace_fields_load_safely_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "source_run"
            source_dir.mkdir()
            (source_dir / "odds_snapshot.csv").write_text("run_id\nlegacy\n", encoding="utf-8")
            (source_dir / "xg_snapshot.csv").write_text("run_id\nlegacy\n", encoding="utf-8")

            resolved = _resolve_source_run(source_dir)
            contract = resolved["replay_input_contract"]

            self.assertEqual(contract["source_strength"], "strong")
            self.assertEqual(contract["replay_quality_status"], "strong_frozen_inputs_trace_incomplete")
            self.assertIn("decision_timestamp", contract["missing_trace_fields"])
            self.assertIn("temporal_contract_not_complete", contract["replay_limitations"])

    def test_legacy_ledger_and_dashboard_load_without_temporal_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "ledger.csv"
            pick = {
                "bet_id": "bet_test",
                "run_id": "run_test",
                "generated_at": "2026-04-24 12:00:00",
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
                "odd_entrada": 2.0,
                "odd_justa": 1.8,
                "prob_model": 0.55,
                "ev_percent": 10.0,
                "confidence_score": 4,
                "stake_units": 0.5,
                "entry_reason": "EDGE_MODERADO",
                "risk_flags": "SEM_FLAG",
            }

            append_new_picks_to_ledger(pd.DataFrame([pick]), ledger_file)
            loaded = load_ledger(ledger_file)
            payload = build_dashboard_payload(loaded, entries_limit=10)

            self.assertIn("odds_snapshot_time", loaded.columns)
            self.assertIn("xg_asof", loaded.columns)
            self.assertEqual(payload["entries"][0].get("odds_snapshot_time", ""), "")
            self.assertEqual(payload["entries"][0].get("temporal_contract_status", ""), "")


if __name__ == "__main__":
    unittest.main()
