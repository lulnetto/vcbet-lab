from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from vcbet.core.line_selector import select_top_picks
from vcbet.core.selection.entry_quality import compute_entry_quality
from vcbet.core.strategy_config import configure_runtime


def _configure_portfolio(max_picks_per_match: int = 4) -> None:
    payload = {
        "metadata": {"name": "portfolio_correlation_test"},
        "rules": {
            "portfolio": {
                "max_picks_per_match": max_picks_per_match,
                "max_picks_per_league": None,
                "max_stake_per_league": None,
                "max_picks_per_market_family": None,
                "max_stake_per_market_family": None,
                "near_duplicate_line_tolerance": 0.25,
                "contradictory_line_tolerance": 0.25,
                "medium_correlation_policy": "downgrade",
                "correlation_selection": {
                    "enabled": True,
                    "max_picks_per_high_correlation_cluster": 1,
                    "ev_gap_override_pp": 2.0,
                },
            }
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "portfolio_correlation_test.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        configure_runtime(config_file=path)


def _candidate(
    bet_id: str,
    *,
    match_name: str = "Home FC - Away FC",
    league: str = "Liga Test",
    market_type: str,
    side: str,
    line,
    target_team_role: str = "geral",
    target_team_name: str = "geral",
    selection_raw: str,
    ev_percent: float,
    confidence_score: float = 5,
    odd_entrada: float = 1.9,
) -> dict:
    home_team, away_team = match_name.split(" - ", 1)
    return {
        "bet_id": bet_id,
        "run_id": "run_test",
        "league": league,
        "match_datetime": "2026-05-01 15:00",
        "home_team": home_team,
        "away_team": away_team,
        "match_name": match_name,
        "market_type": market_type,
        "market_scope": "full_time",
        "market_raw": market_type,
        "selection_raw": selection_raw,
        "side": side,
        "line": line,
        "target_team_role": target_team_role,
        "target_team_name": target_team_name,
        "odd_entrada": odd_entrada,
        "odd_justa": 1.7,
        "prob_model": 0.55,
        "ev_percent": ev_percent,
        "confidence_score": confidence_score,
        "stake_units": 1.0,
        "risk_flags": "SEM_FLAG",
    }


def _row_by_bet_id(df: pd.DataFrame, bet_id: str) -> pd.Series:
    return df.loc[df["bet_id"] == bet_id].iloc[0]


class PortfolioCorrelationSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        _configure_portfolio()

    def test_dnb_loses_to_ah_plus_025_when_ev_gap_below_relation_threshold(self) -> None:
        rows = [
            _candidate(
                "mallorca_dnb",
                match_name="Girona FC - Mallorca",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca",
                ev_percent=18.56,
            ),
            _candidate(
                "mallorca_ah025",
                match_name="Girona FC - Mallorca",
                market_type="asian_handicap",
                side="away",
                line=0.25,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca +0.25",
                ev_percent=14.96,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["mallorca_ah025"])
        rejected_dnb = _row_by_bet_id(rejected, "mallorca_dnb")
        self.assertEqual(rejected_dnb["portfolio_reject_reason"], "HIGH_CORRELATION_LOWER_SCORE")
        self.assertEqual(rejected_dnb["relation_override_key"], "DNB_AH_PLUS_0_25")
        self.assertEqual(float(rejected_dnb["relation_ev_gap_required_pp"]), 4.0)
        self.assertAlmostEqual(float(rejected_dnb["relation_ev_gap_actual_pp"]), 3.60)
        self.assertEqual(rejected_dnb["relation_preferred_by"], "protection")
        self.assertEqual(rejected_dnb["relation_preferred_reason"], "protected_line_wins_ev_gap_below_threshold")

    def test_three_way_dnb_does_not_win_after_losing_to_ah_plus_025(self) -> None:
        rows = [
            _candidate(
                "mallorca_dnb",
                match_name="Girona FC - Mallorca",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca",
                ev_percent=18.56,
            ),
            _candidate(
                "mallorca_ah025",
                match_name="Girona FC - Mallorca",
                market_type="asian_handicap",
                side="away",
                line=0.25,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca +0.25",
                ev_percent=14.96,
            ),
            _candidate(
                "mallorca_ah05",
                match_name="Girona FC - Mallorca",
                market_type="asian_handicap",
                side="away",
                line=0.5,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca +0.5",
                ev_percent=11.49,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["mallorca_ah025"])
        self.assertEqual(selected.iloc[0]["relation_override_key"], "DNB_AH_PLUS_0_25")
        rejected_dnb = _row_by_bet_id(rejected, "mallorca_dnb")
        self.assertEqual(rejected_dnb["relation_override_key"], "DNB_AH_PLUS_0_25")
        self.assertAlmostEqual(float(rejected_dnb["relation_ev_gap_actual_pp"]), 3.60)
        self.assertEqual(rejected_dnb["relation_preferred_by"], "protection")

    def test_dnb_beats_ah_plus_025_when_ev_gap_reaches_relation_threshold(self) -> None:
        rows = [
            _candidate(
                "mallorca_dnb",
                match_name="Girona FC - Mallorca",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca",
                ev_percent=19.10,
            ),
            _candidate(
                "mallorca_ah025",
                match_name="Girona FC - Mallorca",
                market_type="asian_handicap",
                side="away",
                line=0.25,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca +0.25",
                ev_percent=14.90,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["mallorca_dnb"])
        self.assertEqual(selected.iloc[0]["relation_override_key"], "DNB_AH_PLUS_0_25")
        self.assertEqual(selected.iloc[0]["relation_preferred_by"], "ev_gap")
        self.assertAlmostEqual(float(selected.iloc[0]["relation_ev_gap_actual_pp"]), 4.20)
        self.assertEqual(_row_by_bet_id(rejected, "mallorca_ah025")["relation_preferred_by"], "ev_gap")

    def test_dnb_loses_to_ah_plus_05_when_ev_gap_below_relation_threshold(self) -> None:
        rows = [
            _candidate(
                "mallorca_dnb",
                match_name="Girona FC - Mallorca",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca",
                ev_percent=16.00,
            ),
            _candidate(
                "mallorca_ah05",
                match_name="Girona FC - Mallorca",
                market_type="asian_handicap",
                side="away",
                line=0.5,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca +0.5",
                ev_percent=11.00,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["mallorca_ah05"])
        rejected_dnb = _row_by_bet_id(rejected, "mallorca_dnb")
        self.assertEqual(rejected_dnb["relation_override_key"], "DNB_AH_PLUS_0_5")
        self.assertEqual(float(rejected_dnb["relation_ev_gap_required_pp"]), 6.0)
        self.assertAlmostEqual(float(rejected_dnb["relation_ev_gap_actual_pp"]), 5.00)
        self.assertEqual(rejected_dnb["relation_preferred_by"], "protection")

    def test_dnb_beats_ah_plus_05_when_ev_gap_reaches_relation_threshold(self) -> None:
        rows = [
            _candidate(
                "mallorca_dnb",
                match_name="Girona FC - Mallorca",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca",
                ev_percent=18.00,
            ),
            _candidate(
                "mallorca_ah05",
                match_name="Girona FC - Mallorca",
                market_type="asian_handicap",
                side="away",
                line=0.5,
                target_team_role="away",
                target_team_name="Mallorca",
                selection_raw="Mallorca +0.5",
                ev_percent=11.50,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["mallorca_dnb"])
        self.assertEqual(selected.iloc[0]["relation_override_key"], "DNB_AH_PLUS_0_5")
        self.assertEqual(selected.iloc[0]["relation_preferred_by"], "ev_gap")
        self.assertAlmostEqual(float(selected.iloc[0]["relation_ev_gap_actual_pp"]), 6.50)
        self.assertEqual(_row_by_bet_id(rejected, "mallorca_ah05")["portfolio_reject_reason"], "HIGH_CORRELATION_LOWER_SCORE")

    def test_dnb_vs_ah_zero_equivalent_keeps_higher_ev(self) -> None:
        rows = [
            _candidate(
                "granada_dnb",
                match_name="Real Zaragoza - Granada",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Granada",
                selection_raw="Granada",
                ev_percent=14.0,
            ),
            _candidate(
                "granada_ah0",
                match_name="Real Zaragoza - Granada",
                market_type="asian_handicap",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Granada",
                selection_raw="Granada 0.0",
                ev_percent=18.0,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["granada_ah0"])
        self.assertEqual(selected.iloc[0]["relation_override_key"], "DNB_EQUALS_AH_0")
        self.assertEqual(selected.iloc[0]["relation_preferred_by"], "equivalent_ev")
        rejected_dnb = _row_by_bet_id(rejected, "granada_dnb")
        self.assertEqual(rejected_dnb["portfolio_reject_reason"], "EQUIVALENT_MARKET_LOWER_SCORE")
        self.assertEqual(rejected_dnb["correlation_reason"], "DNB_EQUALS_AH_0")
        self.assertEqual(rejected_dnb["relation_override_key"], "DNB_EQUALS_AH_0")

    def test_ah_minus_025_needs_two_ev_points_to_beat_dnb(self) -> None:
        rows = [
            _candidate(
                "granada_dnb",
                match_name="Real Zaragoza - Granada",
                market_type="draw_no_bet",
                side="away",
                line=0.0,
                target_team_role="away",
                target_team_name="Granada",
                selection_raw="Granada",
                ev_percent=12.0,
            ),
            _candidate(
                "granada_ah_minus_025",
                match_name="Real Zaragoza - Granada",
                market_type="asian_handicap",
                side="away",
                line=-0.25,
                target_team_role="away",
                target_team_name="Granada",
                selection_raw="Granada -0.25",
                ev_percent=13.0,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["granada_dnb"])
        self.assertEqual(selected.iloc[0]["relation_override_key"], "DNB_AH_MINUS_0_25")
        self.assertEqual(selected.iloc[0]["relation_preferred_by"], "protection")
        self.assertEqual(float(selected.iloc[0]["relation_ev_gap_required_pp"]), 2.0)
        self.assertAlmostEqual(float(selected.iloc[0]["relation_ev_gap_actual_pp"]), 1.0)
        self.assertEqual(_row_by_bet_id(rejected, "granada_ah_minus_025")["relation_preferred_by"], "protection")

    def test_btts_yes_vs_team_total_over_05_keeps_one_by_score(self) -> None:
        rows = [
            _candidate(
                "leeds_btts_yes",
                match_name="Leeds United - Burnley",
                market_type="btts",
                side="yes",
                line=None,
                selection_raw="Sim",
                ev_percent=12.0,
            ),
            _candidate(
                "burnley_tt_over05",
                match_name="Leeds United - Burnley",
                market_type="team_total",
                side="over",
                line=0.5,
                target_team_role="away",
                target_team_name="Burnley",
                selection_raw="Burnley Mais de 0.5",
                ev_percent=12.0,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected.iloc[0]["portfolio_reject_reason"], "HIGH_CORRELATION_LOWER_SCORE")
        self.assertGreaterEqual(
            float(selected.iloc[0]["portfolio_selection_score"]),
            float(rejected.iloc[0]["portfolio_selection_score"]),
        )

    def test_total_over_25_loses_to_asian_over_20_when_ev_gap_below_threshold(self) -> None:
        rows = [
            _candidate(
                "shakhtar_total_over25",
                match_name="FC Shakhtar Donetsk - Crystal Palace",
                market_type="total_goals",
                side="over",
                line=2.5,
                selection_raw="Mais de 2.5",
                ev_percent=18.86,
            ),
            _candidate(
                "shakhtar_asian_over20",
                match_name="FC Shakhtar Donetsk - Crystal Palace",
                market_type="asian_total",
                side="over",
                line=2.0,
                selection_raw="Mais de 2.0",
                ev_percent=14.09,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["shakhtar_asian_over20"])
        rejected_total = _row_by_bet_id(rejected, "shakhtar_total_over25")
        self.assertEqual(rejected_total["relation_override_key"], "TOTAL_OVER_PROTECTED_LINE")
        self.assertEqual(float(rejected_total["relation_ev_gap_required_pp"]), 5.0)
        self.assertAlmostEqual(float(rejected_total["relation_ev_gap_actual_pp"]), 4.77)
        self.assertEqual(rejected_total["relation_preferred_by"], "protection")
        self.assertEqual(
            rejected_total["relation_preferred_reason"],
            "protected_total_line_wins_ev_gap_below_threshold",
        )

    def test_total_over_25_beats_asian_over_20_when_ev_gap_reaches_threshold(self) -> None:
        rows = [
            _candidate(
                "total_over25",
                market_type="total_goals",
                side="over",
                line=2.5,
                selection_raw="Mais de 2.5",
                ev_percent=20.00,
            ),
            _candidate(
                "asian_over20",
                market_type="asian_total",
                side="over",
                line=2.0,
                selection_raw="Mais de 2.0",
                ev_percent=14.50,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["total_over25"])
        self.assertEqual(selected.iloc[0]["relation_override_key"], "TOTAL_OVER_PROTECTED_LINE")
        self.assertEqual(selected.iloc[0]["relation_preferred_by"], "ev_gap")
        self.assertEqual(
            selected.iloc[0]["relation_preferred_reason"],
            "less_protected_total_line_wins_ev_gap_threshold_met",
        )
        self.assertEqual(_row_by_bet_id(rejected, "asian_over20")["relation_preferred_by"], "ev_gap")

    def test_total_under_25_loses_to_asian_under_30_when_gap_below_threshold(self) -> None:
        rows = [
            _candidate(
                "total_under25",
                market_type="total_goals",
                side="under",
                line=2.5,
                selection_raw="Menos de 2.5",
                ev_percent=13.0,
            ),
            _candidate(
                "asian_under30",
                market_type="asian_total",
                side="under",
                line=3.0,
                selection_raw="Menos de 3.0",
                ev_percent=10.0,
            ),
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(selected["bet_id"].tolist(), ["asian_under30"])
        rejected_total = _row_by_bet_id(rejected, "total_under25")
        self.assertEqual(rejected_total["relation_override_key"], "TOTAL_UNDER_PROTECTED_LINE")
        self.assertEqual(float(rejected_total["relation_ev_gap_required_pp"]), 5.0)
        self.assertAlmostEqual(float(rejected_total["relation_ev_gap_actual_pp"]), 3.0)
        self.assertEqual(rejected_total["relation_preferred_by"], "protection")

    def test_entry_quality_rewards_protected_line_and_odds_balance(self) -> None:
        ah_quality = compute_entry_quality(
            _candidate(
                "freiburg_ah025",
                market_type="asian_handicap",
                side="home",
                line=0.25,
                target_team_role="home",
                target_team_name="Freiburg",
                selection_raw="Freiburg +0.25",
                ev_percent=15.0,
                odd_entrada=1.90,
            )
        )
        dnb_quality = compute_entry_quality(
            _candidate(
                "freiburg_dnb",
                market_type="draw_no_bet",
                side="home",
                line=0.0,
                target_team_role="home",
                target_team_name="Freiburg",
                selection_raw="Freiburg",
                ev_percent=16.0,
                odd_entrada=2.50,
            )
        )

        self.assertGreaterEqual(ah_quality["entry_quality_score"], dnb_quality["entry_quality_score"])
        self.assertGreater(
            ah_quality["entry_quality_line_protection_component"],
            dnb_quality["entry_quality_line_protection_component"],
        )
        self.assertGreater(ah_quality["entry_quality_odds_component"], dnb_quality["entry_quality_odds_component"])

    def test_low_sample_residual_reduces_entry_quality(self) -> None:
        base = _candidate(
            "candidate",
            market_type="total_goals",
            side="over",
            line=2.5,
            selection_raw="Mais de 2.5",
            ev_percent=12.0,
        )
        adjusted = compute_entry_quality({**base, "xg_observational_flags": "GD_XG_RESIDUAL_ADJUSTED"})
        low_sample = compute_entry_quality(
            {**base, "xg_observational_flags": "GD_XG_RESIDUAL_NOT_APPLIED_LOW_SAMPLE"}
        )

        self.assertGreater(adjusted["entry_quality_score"], low_sample["entry_quality_score"])
        self.assertEqual(low_sample["entry_quality_data_component"], -1)

    def test_disabled_league_and_family_caps_do_not_reject_good_picks(self) -> None:
        rows = [
            _candidate(
                f"pick_{idx}",
                match_name=f"Home {idx} - Away {idx}",
                market_type="total_goals",
                side="over",
                line=2.5,
                selection_raw="Mais de 2.5",
                ev_percent=10.0 + idx,
            )
            for idx in range(4)
        ]

        selected, rejected = select_top_picks(pd.DataFrame(rows), return_meta=True)

        self.assertEqual(len(selected), 4)
        self.assertNotIn("LEAGUE_PICK_LIMIT", set(rejected.get("portfolio_reject_reason", pd.Series(dtype=object))))
        self.assertNotIn("MARKET_FAMILY_PICK_LIMIT", set(rejected.get("portfolio_reject_reason", pd.Series(dtype=object))))


if __name__ == "__main__":
    unittest.main()
