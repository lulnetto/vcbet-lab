from __future__ import annotations

import dataclasses
import unittest

from vcbet.domain.contracts import (
    BetRecord,
    LedgerAppendResult,
    NormalizedMarket,
    OddsSnapshot,
    PricingResult,
    XGSnapshot,
)


class DomainContractsTest(unittest.TestCase):
    def test_basic_contract_construction(self) -> None:
        market = NormalizedMarket(
            market_type="asian_total",
            scope="full_time",
            side="over",
            line=2.75,
            target="geral",
            raw_market="Asiatico Total",
            raw_selection="Mais de 2.75",
        )
        odds = OddsSnapshot(
            collected_at="2026-04-24 12:00:00",
            kickoff="2026-04-24 15:00:00",
            source="betano",
            markets=(market,),
            source_run_id="run_test",
        )
        xg = XGSnapshot(
            collected_at="2026-04-24 11:55:00",
            source="footystats",
            team_rows=({"team": "Casa FC", "xg": 1.4},),
        )
        pricing = PricingResult(
            prob_model=0.52,
            fair_odds=1.92,
            ev_percent=9.2,
            lambda_home=1.3,
            lambda_away=1.1,
            method="poisson",
        )
        append_result = LedgerAppendResult(appended=1, blocked=0, duplicate=0, messages=("ok",))

        self.assertEqual(odds.markets[0], market)
        self.assertEqual(xg.team_rows[0]["team"], "Casa FC")
        self.assertEqual(pricing.method, "poisson")
        self.assertEqual(append_result.messages, ("ok",))

    def test_dataclasses_asdict_serialization_is_plain(self) -> None:
        record = BetRecord(
            bet_id="bet_001",
            run_id="run_test",
            league="Liga Teste",
            match_name="Casa FC - Fora FC",
            market_type="total_goals",
            market_scope="full_time",
            side="over",
            line=2.5,
            selection_raw="Mais de 2.5",
            odd_entrada=2.1,
            final_bet_status="open",
            sofascore_event_id="14083330",
        )

        payload = dataclasses.asdict(record)

        self.assertEqual(payload["bet_id"], "bet_001")
        self.assertEqual(payload["sofascore_event_id"], "14083330")
        self.assertEqual(payload["extra_fields"], {})

    def test_contracts_do_not_import_pandas(self) -> None:
        import vcbet.domain.contracts as contracts

        self.assertNotIn("pandas", contracts.__dict__)
        self.assertNotIn("pd", contracts.__dict__)

    def test_bet_record_represents_old_rows_missing_sofascore_event_id(self) -> None:
        legacy_row = {
            "bet_id": "legacy_001",
            "run_id": "run_old",
            "league": "Liga Teste",
            "match_datetime": "2026-04-24 15:00:00",
            "home_team": "Casa FC",
            "away_team": "Fora FC",
            "match_name": "Casa FC - Fora FC",
            "market_type": "total_goals",
            "market_scope": "full_time",
            "side": "over",
            "line": "2.5",
            "selection_raw": "Mais de 2.5",
            "odd_entrada": "2.10",
            "final_bet_status": "open",
            "unknown_legacy_column": "kept",
        }

        record = BetRecord.from_mapping(legacy_row)
        payload = record.to_mapping()

        self.assertIsNone(record.sofascore_event_id)
        self.assertIsNone(record.source_event_id)
        self.assertEqual(record.final_bet_status, "open")
        self.assertEqual(payload["unknown_legacy_column"], "kept")

    def test_source_event_id_is_compatible_with_sofascore_event_id(self) -> None:
        record = BetRecord.from_mapping({"bet_id": "bet_001", "source_event_id": "14083330"})

        self.assertEqual(record.sofascore_event_id, "14083330")
        self.assertEqual(record.source_event_id, "14083330")


if __name__ == "__main__":
    unittest.main()
