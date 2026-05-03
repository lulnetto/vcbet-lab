from __future__ import annotations

import csv
from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.core.pick_features import build_candidate_row
from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.pipeline.output_writer import EXPORT_COLS, candidate_artifact_paths, write_candidate_artifacts
from vcbet.core.pipeline.pricing_stage import build_priced_candidates
from vcbet.core.pipeline.quality_report import build_pre_snapshot_discard_summary
from vcbet.core.pipeline.team_resolution import prepare_team_resolution_state
from vcbet.core.risk_policy import assess_risk_flags, safety_gate_flags
from vcbet.core.market_thresholds import get_critical_flags
from vcbet.core.strategy_config import DEFAULT_CONFIG_PAYLOAD, configure_runtime


class PipelineAuditArtifactsTest(unittest.TestCase):
    def _pricing_fixture(self, config_name: str, xg_rows: list[dict]) -> dict[str, object]:
        runtime = configure_runtime(config_name=config_name)
        df_alvo = pd.DataFrame(
            [
                {
                    "league": "Liga Test",
                    "match_datetime": "2026-05-01 15:00",
                    "home_team": "Home FC",
                    "away_team": "Away FC",
                    "match_name": "Home FC - Away FC",
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
            ]
        )
        df_xg = pd.DataFrame(xg_rows)
        with tempfile.TemporaryDirectory() as tmpdir:
            return build_priced_candidates(
                df_alvo=df_alvo,
                resolution_state=prepare_team_resolution_state(df_xg),
                run_id="run_test",
                odds_run_id="odds_test",
                xg_run_id="xg_test",
                generated_at="2026-05-01 12:00:00",
                alias_pending_file=Path(tmpdir) / "alias_review_pending.csv",
                high_match_threshold=90,
                review_match_threshold=75,
                runtime_config=runtime,
            )

    def _xg_rows_with_residuals(self) -> list[dict]:
        base = {
            "league": "Liga Test",
            "source": "fotmob",
            "xg_split_method": "fotmob_global_duplicated",
        }
        return [
            {
                **base,
                "team_name": "Home FC",
                "xg": 1.5,
                "xga": 1.0,
                "xg_home": 1.5,
                "xg_away": 1.5,
                "xga_home": 1.0,
                "xga_away": 1.0,
                "goals_for_per_match": 2.2,
                "goals_against_per_match": 1.2,
                "xg_raw_total": 30.0,
                "xga_raw_total": 20.0,
                "run_id": "xg_test",
            },
            {
                **base,
                "team_name": "Away FC",
                "xg": 1.1,
                "xga": 1.4,
                "xg_home": 1.1,
                "xg_away": 1.1,
                "xga_home": 1.4,
                "xga_away": 1.4,
                "goals_for_per_match": 1.4,
                "goals_against_per_match": 2.0,
                "xg_raw_total": 22.0,
                "xga_raw_total": 28.0,
                "run_id": "xg_test",
            },
        ]

    def _configure_inline_payload(self, payload: dict) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "strategy.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            configure_runtime(config_file=path)

    def _decision_candidate(self, market_type: str = "asian_total", odd: float = 1.8, league: str = "Liga Test") -> dict:
        return {
            "match_datetime": "2026-05-01 15:00",
            "league": league,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "market_type": market_type,
            "market_scope": "full_time",
            "selection_raw": "Mais de 2.5",
            "side": "over",
            "line": 2.5,
            "target_team_role": "geral",
            "target_team_name": "geral",
            "odd_entrada": odd,
            "odd_justa": 1.55,
            "ev_decimal": 0.15,
            "mu_total": 2.8,
            "match_status_home": "auto_exact",
            "match_status_away": "auto_exact",
            "xg_fallback_home": False,
            "xg_fallback_away": False,
        }

    def test_legacy_v2_keeps_xg_only_pricing(self) -> None:
        pricing = self._pricing_fixture("legacy_v2", self._xg_rows_with_residuals())
        raw = pricing["raw_candidate_rows"][0]

        self.assertEqual(raw["pricing_variant"], "xg_only")
        self.assertFalse(raw["xg_residual_adjustment_enabled"])
        self.assertAlmostEqual(raw["lambda_home_base"], raw["lambda_home_adjusted"])
        self.assertAlmostEqual(raw["lambda_away_base"], raw["lambda_away_adjusted"])
        self.assertAlmostEqual(raw["odd_justa"], raw["odd_justa_base"])
        self.assertAlmostEqual(raw["ev_decimal"] * 100, raw["ev_percent_base"])

    def test_gd_experimental_pricing_exports_adjusted_ev_fields(self) -> None:
        pricing = self._pricing_fixture("gd_experimental_v1", self._xg_rows_with_residuals())
        raw = pricing["raw_candidate_rows"][0]

        self.assertEqual(raw["pricing_variant"], "xg_residual_adjusted_v1")
        self.assertTrue(raw["xg_residual_adjustment_enabled"])
        self.assertIn("odd_justa_adjusted", raw)
        self.assertIn("ev_percent_adjusted", raw)
        self.assertIn("lambda_home_adjusted", raw)
        self.assertNotEqual(raw["lambda_home_adjusted"], raw["lambda_home_base"])
        self.assertAlmostEqual(raw["odd_justa"], raw["odd_justa_adjusted"])
        self.assertAlmostEqual(raw["ev_decimal"] * 100, raw["ev_percent_adjusted"])

    def test_gd_xg_observational_flags_do_not_block_safety_gate(self) -> None:
        configure_runtime(config_name="gd_experimental_v1")
        gd_flags = {
            "GD_XG_ALIGNED",
            "GD_XG_ATTACK_OVERPERFORMANCE",
            "GD_XG_ATTACK_UNDERPERFORMANCE",
            "GD_XG_DEFENSE_OVERPERFORMANCE",
            "GD_XG_DEFENSE_UNDERPERFORMANCE",
            "GD_XG_RESIDUAL_ADJUSTED",
            "GD_XG_RESIDUAL_NOT_APPLIED_LOW_SAMPLE",
        }

        self.assertEqual(safety_gate_flags(sorted(gd_flags)), [])
        self.assertFalse(gd_flags.intersection(get_critical_flags()))

    def test_enabled_markets_blocks_disabled_market_in_pick_filter(self) -> None:
        payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
        payload["enabled_markets"] = ["asian_total"]
        self._configure_inline_payload(payload)

        evaluated, reason, rejected = evaluate_pick_candidate_with_details(self._decision_candidate(market_type="btts"))

        self.assertIsNone(evaluated)
        self.assertEqual(reason, "market_disabled_by_config")
        self.assertEqual(rejected["safety_reject_reason"], "market_disabled_by_config")

    def test_allowed_odd_ranges_gate_candidates(self) -> None:
        payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
        payload["allowed_odd_ranges"] = [{"min": 1.5, "max": 2.0}, {"min": 2.5, "max": 3.0}]
        payload["markets"]["asian_total"]["standard_max"] = 3.0
        payload["markets"]["asian_total"]["extended_max"] = 3.2
        self._configure_inline_payload(payload)

        blocked, blocked_reason, _ = evaluate_pick_candidate_with_details(self._decision_candidate(odd=2.2))
        low_range, low_reason, _ = evaluate_pick_candidate_with_details(self._decision_candidate(odd=1.8))
        high_range, high_reason, _ = evaluate_pick_candidate_with_details(self._decision_candidate(odd=2.7))

        self.assertIsNone(blocked)
        self.assertEqual(blocked_reason, "odd_outside_allowed_ranges")
        self.assertIsNotNone(low_range)
        self.assertIsNone(low_reason)
        self.assertIsNotNone(high_range)
        self.assertIsNone(high_reason)

    def test_league_filter_allowlist_blocks_unlisted_league(self) -> None:
        payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
        payload["league_filter"] = {
            "enabled": True,
            "mode": "allowlist",
            "allowed_leagues": ["Liga Permitida"],
            "blocked_leagues": [],
        }
        self._configure_inline_payload(payload)

        blocked, blocked_reason, _ = evaluate_pick_candidate_with_details(self._decision_candidate(league="Liga Test"))
        allowed, allowed_reason, _ = evaluate_pick_candidate_with_details(self._decision_candidate(league="Liga Permitida"))

        self.assertIsNone(blocked)
        self.assertEqual(blocked_reason, "league_disabled_by_config")
        self.assertIsNotNone(allowed)
        self.assertIsNone(allowed_reason)

    def test_match_fuzzy_still_blocks_safety_gate(self) -> None:
        configure_runtime(config_name="legacy_v2")
        candidate = {
            "market_type": "total_goals",
            "line": 2.5,
            "odd_entrada": 2.0,
            "mu_total": 2.8,
            "match_status_home": "auto_fuzzy_high",
            "match_status_away": "auto_exact",
            "xg_fallback_home": False,
            "xg_fallback_away": False,
            "league": "Liga Europa",
        }

        flags = assess_risk_flags(candidate)

        self.assertIn("MATCH_FUZZY", flags)
        self.assertIn("MATCH_FUZZY", safety_gate_flags(flags))

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

    def test_quality_fields_are_declared_for_pick_and_rejection_outputs(self) -> None:
        expected = {
            "entry_quality_score",
            "entry_quality_tier",
            "entry_quality_reasons",
            "entry_quality_market_component",
            "entry_quality_line_protection_component",
            "entry_quality_odds_component",
            "entry_quality_data_component",
            "entry_quality_risk_component",
            "entry_quality_ev_component",
        }
        self.assertTrue(expected.issubset(set(EXPORT_COLS)))

        rejected = {
            "bet_id": "rejected_1",
            "portfolio_reject_reason": "HIGH_CORRELATION_LOWER_SCORE",
            "entry_quality_score": 62,
            "entry_quality_tier": "C",
            "entry_quality_reasons": "ev_12_18|line_total_over_2_5",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = candidate_artifact_paths(Path(tmpdir))
            write_candidate_artifacts(
                df_raw_candidates=pd.DataFrame(),
                df_candidates=pd.DataFrame(),
                df_blocked_candidates=pd.DataFrame(),
                df_portfolio_rejected=pd.DataFrame([rejected]),
                artifact_paths=paths,
            )
            rejected_df = pd.read_csv(paths["portfolio_rejected_file"], sep=";")

        self.assertTrue({"entry_quality_score", "entry_quality_tier", "entry_quality_reasons"}.issubset(rejected_df.columns))

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
