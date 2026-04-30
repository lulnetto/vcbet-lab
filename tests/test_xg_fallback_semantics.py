from __future__ import annotations

import unittest

from vcbet.core.risk_policy import assess_risk_flags, resolve_xg_fallback_flag
from vcbet.core.decision_policy import _confidence_score
from vcbet.core.market_thresholds import get_critical_flags


class ResolveXgFallbackFlagTest(unittest.TestCase):
    def test_fotmob_source_returns_fotmob_global_xg(self) -> None:
        self.assertEqual(resolve_xg_fallback_flag("fotmob", "anything"), "FOTMOB_GLOBAL_XG")

    def test_fotmob_split_method_returns_fotmob_global_xg(self) -> None:
        self.assertEqual(resolve_xg_fallback_flag("other", "fotmob_global_duplicated"), "FOTMOB_GLOBAL_XG")

    def test_generic_global_duplicated_returns_fallback_xg_global(self) -> None:
        self.assertEqual(resolve_xg_fallback_flag("footystats", "global_duplicated"), "FALLBACK_XG_GLOBAL")

    def test_no_fallback_returns_none(self) -> None:
        self.assertIsNone(resolve_xg_fallback_flag("footystats", "footystats_global"))


class AssessRiskFlagsSourceAwareTest(unittest.TestCase):
    def _base_candidate(self, **overrides) -> dict:
        return {
            "market_type": "total_goals",
            "line": 2.5,
            "odd_entrada": 2.0,
            "mu_total": 2.8,
            "match_status_home": "auto_exact",
            "match_status_away": "auto_exact",
            "league": "Premier League",
            "xg_fallback_home": False,
            "xg_fallback_away": False,
            "xg_source_home": "",
            "xg_source_away": "",
            "xg_split_method_home": "",
            "xg_split_method_away": "",
            **overrides,
        }

    def test_fotmob_global_generates_fotmob_global_xg_not_fallback(self) -> None:
        candidate = self._base_candidate(
            xg_fallback_home=True,
            xg_fallback_away=True,
            xg_source_home="fotmob",
            xg_source_away="fotmob",
            xg_split_method_home="fotmob_global_duplicated",
            xg_split_method_away="fotmob_global_duplicated",
        )
        flags = assess_risk_flags(candidate)
        self.assertIn("FOTMOB_GLOBAL_XG", flags)
        self.assertNotIn("FALLBACK_XG_GLOBAL", flags)

    def test_real_fallback_generates_fallback_xg_global(self) -> None:
        candidate = self._base_candidate(
            xg_fallback_home=True,
            xg_fallback_away=True,
            xg_source_home="footystats",
            xg_source_away="footystats",
            xg_split_method_home="global_duplicated",
            xg_split_method_away="global_duplicated",
        )
        flags = assess_risk_flags(candidate)
        self.assertIn("FALLBACK_XG_GLOBAL", flags)
        self.assertNotIn("FOTMOB_GLOBAL_XG", flags)

    def test_fotmob_global_does_not_add_dado_incompleto_liga(self) -> None:
        candidate = self._base_candidate(
            market_type="team_total",
            xg_fallback_home=True,
            xg_fallback_away=True,
            xg_source_home="fotmob",
            xg_source_away="fotmob",
            xg_split_method_home="fotmob_global_duplicated",
            xg_split_method_away="fotmob_global_duplicated",
        )
        flags = assess_risk_flags(candidate)
        self.assertIn("FOTMOB_GLOBAL_XG", flags)
        self.assertNotIn("DADO_INCOMPLETO_LIGA", flags)

    def test_real_fallback_adds_dado_incompleto_liga_for_team_total(self) -> None:
        candidate = self._base_candidate(
            market_type="team_total",
            xg_fallback_home=True,
            xg_fallback_away=False,
            xg_source_home="footystats",
            xg_source_away="footystats",
            xg_split_method_home="global_duplicated",
            xg_split_method_away="footystats_global",
        )
        flags = assess_risk_flags(candidate)
        self.assertIn("FALLBACK_XG_GLOBAL", flags)
        self.assertIn("DADO_INCOMPLETO_LIGA", flags)

    def test_mixed_fotmob_and_real_fallback_generates_both(self) -> None:
        candidate = self._base_candidate(
            xg_fallback_home=True,
            xg_fallback_away=True,
            xg_source_home="fotmob",
            xg_source_away="footystats",
            xg_split_method_home="fotmob_global_duplicated",
            xg_split_method_away="global_duplicated",
        )
        flags = assess_risk_flags(candidate)
        self.assertIn("FOTMOB_GLOBAL_XG", flags)
        self.assertIn("FALLBACK_XG_GLOBAL", flags)


class CriticalFlagsTest(unittest.TestCase):
    def test_fotmob_global_xg_is_not_critical(self) -> None:
        critical = get_critical_flags()
        self.assertNotIn("FOTMOB_GLOBAL_XG", critical)

    def test_fallback_xg_global_is_not_critical(self) -> None:
        # sanity check: fallback real também não deveria ser critical
        critical = get_critical_flags()
        self.assertNotIn("FALLBACK_XG_GLOBAL", critical)


class ConfidenceScoreSourceAwareTest(unittest.TestCase):
    def _base_candidate(self, **overrides) -> dict:
        return {
            "market_type": "total_goals",
            "ev_decimal": 0.12,
            "match_status_home": "auto_exact",
            "match_status_away": "auto_exact",
            "league": "Premier League",
            **overrides,
        }

    def test_fotmob_global_xg_keeps_complete_data_bonus(self) -> None:
        candidate = self._base_candidate()
        flags = ["FOTMOB_GLOBAL_XG"]
        score, reasons, cap = _confidence_score(candidate, flags)
        self.assertIn("DADO_COMPLETO", reasons)

    def test_real_fallback_xg_global_loses_complete_data_bonus(self) -> None:
        candidate = self._base_candidate()
        flags = ["FALLBACK_XG_GLOBAL"]
        score, reasons, cap = _confidence_score(candidate, flags)
        self.assertNotIn("DADO_COMPLETO", reasons)


if __name__ == "__main__":
    unittest.main()
