from __future__ import annotations

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.core.candidate_audit import (
    build_candidate_audit,
    write_candidate_audit,
    write_candidate_audit_summary_for_group,
)
from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.line_selector import select_top_picks
from vcbet.core.pipeline.filtering_stage import apply_profile_policies
from vcbet.core.strategy_config import DEFAULT_CONFIG_PAYLOAD, configure_runtime, get_runtime_config


def _candidate(
    key: str,
    *,
    market_type: str,
    side: str,
    selection_raw: str,
    line,
    odd: float = 1.80,
    ev_decimal: float = 0.15,
    target_team_role: str = "geral",
    target_team_name: str = "geral",
) -> dict:
    return {
        "run_id": "run_audit_profile_standard",
        "odds_source_run_id": "source_snapshot_test",
        "xg_source_run_id": "source_snapshot_test",
        "generated_at": "2026-05-04 12:00:00",
        "league": "Liga Test",
        "match_datetime": "2026-05-04 15:00",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "match_name": "Home FC - Away FC",
        "market_type": market_type,
        "market_scope": "full_time",
        "market_raw": market_type,
        "selection_raw": selection_raw,
        "side": side,
        "line": line,
        "target_team_role": target_team_role,
        "target_team_name": target_team_name,
        "event_url": f"https://example.test/{key}",
        "odd": odd,
        "odd_entrada": odd,
        "odd_justa": 1.55,
        "ev_decimal": ev_decimal,
        "mu_total": 3.0,
        "lambda_home": 2.0,
        "lambda_away": 1.0,
        "match_status_home": "auto_exact",
        "match_status_away": "auto_exact",
        "xg_fallback_home": False,
        "xg_fallback_away": False,
        "risk_flags": "SEM_FLAG",
    }


class CandidateAuditExportTest(unittest.TestCase):
    def setUp(self) -> None:
        configure_runtime(config_name="profile_standard")

    def tearDown(self) -> None:
        configure_runtime()

    def _build_profile_audit(self) -> pd.DataFrame:
        raw_rows = [
            _candidate(
                "btts_no",
                market_type="btts",
                side="no",
                selection_raw="Ambas marcam Nao",
                line=None,
            ),
            _candidate(
                "odd_blocked",
                market_type="asian_handicap",
                side="home",
                selection_raw="Home FC 0.0 bloqueada odd",
                line=0.0,
                odd=2.20,
                target_team_role="home",
                target_team_name="Home FC",
            ),
            _candidate(
                "selected_ah",
                market_type="asian_handicap",
                side="home",
                selection_raw="Home FC 0.0",
                line=0.0,
                target_team_role="home",
                target_team_name="Home FC",
            ),
            _candidate(
                "cap_discard",
                market_type="asian_total",
                side="over",
                selection_raw="Mais de 2.5",
                line=2.5,
                odd=1.90,
                ev_decimal=0.14,
            ),
        ]

        approved_rows = []
        blocked_rows = []
        for row in raw_rows:
            evaluated, _reason, rejected = evaluate_pick_candidate_with_details(row)
            if evaluated is not None:
                approved_rows.append(evaluated)
            elif rejected is not None:
                blocked_rows.append(rejected)

        df_candidates = pd.DataFrame(approved_rows)
        df_blocked = pd.DataFrame(blocked_rows)
        df_policy_candidates, df_profile_blocked = apply_profile_policies(df_candidates, get_runtime_config())
        df_final, df_portfolio_rejected = select_top_picks(df_policy_candidates, return_meta=True)

        return build_candidate_audit(
            df_raw_candidates=pd.DataFrame(raw_rows),
            df_candidates=df_candidates,
            df_blocked_candidates=df_blocked,
            df_profile_policy_blocked=df_profile_blocked,
            df_portfolio_rejected=df_portfolio_rejected,
            df_final=df_final,
            runtime_config=get_runtime_config(),
            run_id="run_audit_profile_standard",
            run_group_id="run_group_audit",
            ledger_path="data/ledgers/standard_bets_ledger.csv",
            source_snapshot_id="source_snapshot_test",
        )

    def test_candidate_audit_tracks_policy_and_portfolio_outcomes(self) -> None:
        audit = self._build_profile_audit()

        btts_no = audit.loc[audit["selection"] == "Ambas marcam Nao"].iloc[0]
        self.assertFalse(bool(btts_no["final_selected"]))
        self.assertEqual(btts_no["side_rule_status"], "blocked")
        self.assertEqual(btts_no["sport_sense_reason"], "BTTS_SIDE_BLOCKED")

        odd_blocked = audit.loc[audit["selection"] == "Home FC 0.0 bloqueada odd"].iloc[0]
        self.assertEqual(odd_blocked["odd_policy_status"], "blocked")
        self.assertEqual(odd_blocked["odd_policy_reason"], "ODD_IN_BLOCKED_RANGE")

        portfolio_discard = audit.loc[audit["portfolio_reason"] == "MATCH_PICK_CAP_REACHED"].iloc[0]
        self.assertEqual(portfolio_discard["portfolio_status"], "discarded")
        self.assertFalse(bool(portfolio_discard["final_selected"]))

        selected = audit.loc[audit["final_selected"] == True]  # noqa: E712 - pandas bool selection
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.iloc[0]["portfolio_status"], "selected")

    def test_batch_audit_files_preserve_group_and_source_ids(self) -> None:
        audit = self._build_profile_audit()
        run_group_id = "run_group_candidate_audit_test"
        source_snapshot_id = f"{run_group_id}_source"
        run_date = "2026-05-04"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "runs"
            configs = ["profile_standard", "profile_aggressive"]
            for config_name in configs:
                run_id = f"{run_group_id}_{config_name}"
                run_audit = audit.copy()
                run_audit["run_group_id"] = run_group_id
                run_audit["run_id"] = run_id
                run_audit["config_name"] = config_name
                run_audit["source_snapshot_id"] = source_snapshot_id
                write_candidate_audit(
                    run_audit,
                    output_dir / run_date / run_id / "candidate_audit.csv",
                )

            summary_path = write_candidate_audit_summary_for_group(
                output_dir=output_dir,
                run_group_id=run_group_id,
                run_date=run_date,
                source_snapshot_id=source_snapshot_id,
            )

            audit_files = sorted((output_dir / run_date).glob(f"{run_group_id}_*/candidate_audit.csv"))
            self.assertEqual(len(audit_files), 2)
            self.assertTrue(summary_path.exists())

            loaded = [pd.read_csv(path, sep=";") for path in audit_files]
            combined = pd.concat(loaded, ignore_index=True)
            self.assertEqual(set(combined["run_group_id"]), {run_group_id})
            self.assertEqual(set(combined["source_snapshot_id"]), {source_snapshot_id})
            self.assertEqual(set(combined["config_name"]), set(configs))

    def test_final_selected_count_matches_picks_snapshot_with_max_two_and_equivalence(self) -> None:
        payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
        payload["metadata"] = {"name": "audit_max_two_equivalence"}
        payload["rules"]["portfolio"]["max_picks_per_match"] = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "strategy.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")
            configure_runtime(config_file=config_path)

            raw_rows = [
                _candidate(
                    "under35_a",
                    market_type="total_goals",
                    side="under",
                    selection_raw="Menos de 3.5",
                    line=3.5,
                ),
                _candidate(
                    "under35_b",
                    market_type="total_goals",
                    side="under",
                    selection_raw="Menos de 3.5",
                    line=3.5,
                ),
                _candidate(
                    "ah_home",
                    market_type="asian_handicap",
                    side="home",
                    selection_raw="Home FC +0.5",
                    line=0.5,
                    target_team_role="home",
                    target_team_name="Home FC",
                ),
            ]
            approved_rows = []
            blocked_rows = []
            for row in raw_rows:
                evaluated, _reason, rejected = evaluate_pick_candidate_with_details(row)
                if evaluated is not None:
                    approved_rows.append(evaluated)
                elif rejected is not None:
                    blocked_rows.append(rejected)

            df_candidates = pd.DataFrame(approved_rows)
            df_final, df_portfolio_rejected = select_top_picks(df_candidates, return_meta=True)
            self.assertEqual(len(df_final), 2)
            self.assertEqual(len(df_portfolio_rejected), 1)
            self.assertEqual(df_portfolio_rejected.iloc[0]["portfolio_reject_reason"], "EQUIVALENT_MARKET_LOWER_SCORE")

            picks_snapshot = Path(tmpdir) / "picks_snapshot.csv"
            df_final.to_csv(picks_snapshot, index=False, sep=";", encoding="utf-8-sig")
            picks_df = pd.read_csv(picks_snapshot, sep=";")
            audit = build_candidate_audit(
                df_raw_candidates=pd.DataFrame(raw_rows),
                df_candidates=df_candidates,
                df_blocked_candidates=pd.DataFrame(blocked_rows),
                df_profile_policy_blocked=pd.DataFrame(),
                df_portfolio_rejected=df_portfolio_rejected,
                df_final=picks_df,
                runtime_config=get_runtime_config(),
                run_id="run_audit_max_two",
                run_group_id="run_group_audit",
                ledger_path="data/ledgers/test.csv",
                source_snapshot_id="source_snapshot_test",
            )

        selected = audit.loc[audit["final_selected"] == True]  # noqa: E712 - pandas bool selection
        discarded = audit.loc[audit["portfolio_reason"] == "EQUIVALENT_MARKET_LOWER_SCORE"]
        self.assertEqual(len(selected), len(picks_df))
        self.assertEqual(len(audit.loc[audit["portfolio_reason"] == "SELECTED"]), len(picks_df))
        self.assertEqual(len(discarded), 1)
        self.assertFalse(bool(discarded.iloc[0]["final_selected"]))
        self.assertEqual(discarded.iloc[0]["portfolio_status"], "discarded")
        self.assertEqual(discarded.iloc[0]["final_reject_reason"], "EQUIVALENT_MARKET_LOWER_SCORE")

    def test_policy_diagnostics_run_when_earlier_gate_blocked_candidate(self) -> None:
        configure_runtime(config_name="profile_aggressive")
        raw_rows = [
            _candidate(
                "btts_no_odd_blocked",
                market_type="btts",
                side="no",
                selection_raw="Ambas marcam Nao",
                line=None,
                odd=2.20,
            ),
            _candidate(
                "team_total_semantic_odd_blocked",
                market_type="team_total",
                side="over",
                selection_raw="Away FC Mais de 1.5",
                line=1.5,
                odd=2.20,
                target_team_role="away",
                target_team_name="Away FC",
            ),
        ]
        blocked_rows = []
        for row in raw_rows:
            evaluated, reason, rejected = evaluate_pick_candidate_with_details(row)
            self.assertIsNone(evaluated)
            self.assertEqual(reason, "odd_in_blocked_range")
            self.assertIsNotNone(rejected)
            blocked_rows.append(rejected)

        audit = build_candidate_audit(
            df_raw_candidates=pd.DataFrame(raw_rows),
            df_candidates=pd.DataFrame(),
            df_blocked_candidates=pd.DataFrame(blocked_rows),
            df_profile_policy_blocked=pd.DataFrame(),
            df_portfolio_rejected=pd.DataFrame(),
            df_final=pd.DataFrame(),
            runtime_config=get_runtime_config(),
            run_id="run_audit_policy_diagnostic",
            run_group_id="run_group_audit",
            ledger_path="data/ledgers/test.csv",
            source_snapshot_id="source_snapshot_test",
        )

        btts_no = audit.loc[audit["selection"] == "Ambas marcam Nao"].iloc[0]
        self.assertEqual(btts_no["final_reject_reason"], "ODD_IN_BLOCKED_RANGE")
        self.assertEqual(btts_no["side_rule_status"], "not_applicable")
        self.assertEqual(btts_no["side_rule_evaluation"], "blocked:BTTS_SIDE_BLOCKED")

        team_total = audit.loc[audit["selection"] == "Away FC Mais de 1.5"].iloc[0]
        self.assertEqual(team_total["final_reject_reason"], "ODD_IN_BLOCKED_RANGE")
        self.assertEqual(team_total["sport_sense_status"], "not_applicable")
        self.assertEqual(team_total["sport_sense_evaluation"], "blocked:UNDERDOG_OVER_AGGRESSIVE_LINE")

    def test_btts_yes_exception_is_audited_and_btts_no_stays_blocked(self) -> None:
        payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
        payload["metadata"] = {"name": "audit_btts_exception"}
        payload["enabled_markets"] = ["btts"]
        payload["allowed_odd_ranges"] = [{"min": 1.65, "max": 2.10}]
        payload["blocked_odd_ranges"] = []
        payload["side_rules"] = {"btts": {"blocked_sides": ["no"]}}
        payload["ev_policy"] = {"min_ev_by_market": {"btts": 0.07}}
        payload["market_exceptions"] = {
            "btts": {
                "yes": {
                    "allow_negative_ev_floor": -0.03,
                    "min_odd": 1.70,
                    "max_odd": 2.05,
                    "requires_sport_sense": True,
                    "stake_cap": 0.5,
                },
                "no": {"blocked": True},
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "strategy.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")
            configure_runtime(config_file=config_path)

            raw_rows = [
                _candidate(
                    "btts_yes_exception",
                    market_type="btts",
                    side="yes",
                    selection_raw="Ambas marcam Sim",
                    line=None,
                    odd=1.80,
                    ev_decimal=-0.02,
                ),
                _candidate(
                    "btts_no_blocked",
                    market_type="btts",
                    side="no",
                    selection_raw="Ambas marcam Nao",
                    line=None,
                    odd=1.80,
                    ev_decimal=0.15,
                ),
            ]
            approved_rows = []
            blocked_rows = []
            for row in raw_rows:
                evaluated, _reason, rejected = evaluate_pick_candidate_with_details(row)
                if evaluated is not None:
                    approved_rows.append(evaluated)
                elif rejected is not None:
                    blocked_rows.append(rejected)

            df_candidates = pd.DataFrame(approved_rows)
            df_policy_candidates, df_profile_blocked = apply_profile_policies(df_candidates, get_runtime_config())
            df_final, df_portfolio_rejected = select_top_picks(df_policy_candidates, return_meta=True)
            audit = build_candidate_audit(
                df_raw_candidates=pd.DataFrame(raw_rows),
                df_candidates=df_candidates,
                df_blocked_candidates=pd.DataFrame(blocked_rows),
                df_profile_policy_blocked=df_profile_blocked,
                df_portfolio_rejected=df_portfolio_rejected,
                df_final=df_final,
                runtime_config=get_runtime_config(),
                run_id="run_audit_btts_exception",
                run_group_id="run_group_audit",
                ledger_path="data/ledgers/test.csv",
                source_snapshot_id="source_snapshot_test",
            )

        btts_yes = audit.loc[audit["selection"] == "Ambas marcam Sim"].iloc[0]
        self.assertTrue(bool(btts_yes["final_selected"]))
        self.assertEqual(btts_yes["ev_policy_reason"], "EV_EXCEPTION_BTTS_YES_EXPERIMENTAL")
        self.assertTrue(bool(btts_yes["market_exception_applied"]))
        self.assertEqual(btts_yes["market_exception_reason"], "EV_EXCEPTION_BTTS_YES_EXPERIMENTAL")
        self.assertLessEqual(float(btts_yes["stake"]), 0.5)

        btts_no = audit.loc[audit["selection"] == "Ambas marcam Nao"].iloc[0]
        self.assertFalse(bool(btts_no["final_selected"]))
        self.assertEqual(btts_no["side_rule_evaluation"], "blocked:BTTS_SIDE_BLOCKED")


if __name__ == "__main__":
    unittest.main()
