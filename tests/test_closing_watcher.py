from __future__ import annotations

import unittest
from datetime import datetime

import pandas as pd

from vcbet.service.closing_watcher import eligible_rows


def official_pick(**overrides) -> dict:
    payload = {
        "bet_id": "bet_phase8_001",
        "run_id": "run_phase8",
        "league": "Liga Teste",
        "match_datetime": "2026-04-24 15:00",
        "home_team": "Casa FC",
        "away_team": "Fora FC",
        "match_name": "Casa FC - Fora FC",
        "market_type": "total_goals",
        "market_scope": "full_time",
        "event_url": "https://example.test/match",
        "selection_raw": "Mais de 2.5",
        "line": 2.5,
        "side": "over",
        "target_team_role": "geral",
        "target_team_name": "geral",
        "odd_entrada": 2.2,
        "stake_units": 1.0,
        "final_bet_status": "open",
        "final_settlement_status": "pending",
    }
    payload.update(overrides)
    return payload


class ClosingWatcherTest(unittest.TestCase):
    def test_eligible_rows_require_event_url_open_status_and_missing_closing_fields(self) -> None:
        now = datetime(2026, 4, 24, 14, 15)
        df = pd.DataFrame(
            [
                official_pick(bet_id="eligible", match_datetime="2026-04-24 15:00"),
                official_pick(bet_id="no_url", event_url="", match_datetime="2026-04-24 15:00"),
                official_pick(bet_id="already_done", closing_odd=1.9, match_datetime="2026-04-24 15:00"),
                official_pick(bet_id="settled", final_bet_status="settled", final_settlement_status="win", match_datetime="2026-04-24 15:00"),
            ]
        )

        rows = eligible_rows(df, now=now, minutes_before=60)

        self.assertEqual(rows["bet_id"].tolist(), ["eligible"])


if __name__ == "__main__":
    unittest.main()
