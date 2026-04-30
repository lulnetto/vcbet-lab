from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.core.pick_features import build_candidate_row
from vcbet.core.pipeline.output_writer import candidate_artifact_paths, write_candidate_artifacts
from vcbet.core.pipeline.quality_report import build_pre_snapshot_discard_summary


class PipelineAuditArtifactsTest(unittest.TestCase):
    def test_blocked_candidates_preserve_market_identity(self) -> None:
        source_row = pd.Series(
            {
                "league": "Liga Test",
                "match_datetime": "2026-04-28 15:00",
                "home_team": "Team A",
                "away_team": "Team B",
                "match_name": "Team A - Team B",
                "market_type": "total_goals",
                "market_scope": "full_time",
                "market_raw": "Total de Gols Mais/Menos",
                "selection_raw": "Mais de 2.5",
                "betano_market_type_id": 13,
                "betano_market_family": "total_goals",
                "normalized_status": "ok",
                "line": 2.5,
                "side": "over",
                "target_team_role": "geral",
                "target_team_name": "geral",
                "event_url": "http://example.com/event",
                "odd": 2.1,
            }
        )
        candidate = build_candidate_row(
            run_id="run_1",
            odds_run_id="odds_run_1",
            xg_run_id="xg_run_1",
            generated_at="2026-04-28 12:00:00",
            row=source_row,
            home_match_status="auto_exact",
            away_match_status="auto_exact",
            home_match_source="test",
            away_match_source="test",
            home_alias_confidence="high",
            away_alias_confidence="high",
            home_registry_file="",
            away_registry_file="",
            lambda_bundle={"mu_total": 2.8, "lambda_home": 1.6, "lambda_away": 1.2},
            pricing_result={
                "probs": {
                    "win": 0.55,
                    "half_win": 0.0,
                    "push": 0.0,
                    "half_loss": 0.0,
                    "loss": 0.45,
                }
            },
            home_xg_row=pd.Series({"xg": 1.5, "xga": 1.1, "xg_home": 1.6, "xga_home": 1.0, "xg_away": 1.3, "xga_away": 1.2}),
            away_xg_row=pd.Series({"xg": 1.2, "xga": 1.4, "xg_home": 1.4, "xga_home": 1.3, "xg_away": 1.1, "xga_away": 1.5}),
        )
        blocked = {
            **candidate,
            "candidate_stage": "blocked_unsafe_candidate",
            "safety_reject_reason": "safety_gate_blocked",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = candidate_artifact_paths(Path(tmpdir))
            write_candidate_artifacts(
                df_raw_candidates=pd.DataFrame([candidate]),
                df_candidates=pd.DataFrame(),
                df_blocked_candidates=pd.DataFrame([blocked]),
                df_portfolio_rejected=pd.DataFrame(),
                artifact_paths=paths,
            )
            blocked_df = pd.read_csv(paths["blocked_candidates_file"], sep=";")

        for column in (
            "run_id",
            "league",
            "match_name",
            "event_url",
            "market_raw",
            "selection_raw",
            "betano_market_type_id",
            "betano_market_family",
            "market_type",
            "side",
            "line",
            "target_team_role",
            "target_team_name",
            "normalized_status",
            "odd",
        ):
            self.assertIn(column, blocked_df.columns)
        self.assertEqual(str(blocked_df.iloc[0]["event_url"]), "http://example.com/event")
        self.assertEqual(int(blocked_df.iloc[0]["betano_market_type_id"]), 13)

    def test_quality_report_pre_snapshot_summary_is_counted_and_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            discard_path = run_dir / "odds_discarded_pre_snapshot.csv"
            with open(discard_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "league",
                        "match_name",
                        "market_raw",
                        "selection_raw",
                        "odd_raw",
                        "betano_market_type_id",
                        "discard_reason",
                    ],
                    delimiter=";",
                )
                writer.writeheader()
                for idx in range(15):
                    writer.writerow(
                        {
                            "league": "Liga Test",
                            "match_name": "A - B",
                            "market_raw": "Resultado Final",
                            "selection_raw": f"Selection {idx}",
                            "odd_raw": "2.0",
                            "betano_market_type_id": "1",
                            "discard_reason": "unsupported_type_id:1",
                        }
                    )

            summary = build_pre_snapshot_discard_summary(run_dir, sample_limit_per_reason=10)

        self.assertEqual(summary["pre_snapshot_discard_counts"], {"unsupported_type_id:1": 15})
        self.assertEqual(len(summary["pre_snapshot_discard_samples"]["unsupported_type_id:1"]), 10)
        self.assertEqual(
            summary["pre_snapshot_discard_samples"]["unsupported_type_id:1"][0]["betano_market_type_id"],
            "1",
        )


if __name__ == "__main__":
    unittest.main()
