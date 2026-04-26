from __future__ import annotations

import multiprocessing
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from vcbet.core.ledger_manager import append_new_picks_to_ledger, load_ledger
from vcbet.core.ledger_portfolio_gate import check_against_open_ledger


def official_pick(**overrides) -> dict:
    payload = {
        "bet_id": "bet_phase8_001",
        "run_id": "run_phase8",
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
        "odd_entrada": 2.2,
        "odd_justa": 1.75,
        "prob_model": 0.57,
        "ev_percent": 20.0,
        "confidence_score": 5,
        "stake_units": 1.0,
        "pick_safety_status": "safe",
        "candidate_stage": "official_accepted_pick",
        "final_bet_status": "open",
        "final_settlement_status": "pending",
        "config_name": "legacy_v2",
    }
    payload.update(overrides)
    return payload


def append_unique_pick_worker(ledger_file: str, worker_index: int, barrier, result_queue) -> None:
    try:
        barrier.wait(timeout=10)
        append_new_picks_to_ledger(
            pd.DataFrame(
                [
                    official_pick(
                        bet_id=f"concurrent_{worker_index}",
                        run_id=f"run_concurrent_{worker_index}",
                        match_datetime=f"2026-04-24 15:{worker_index:02d}",
                        home_team=f"Casa FC {worker_index}",
                        away_team=f"Fora FC {worker_index}",
                        match_name=f"Casa FC {worker_index} - Fora FC {worker_index}",
                        event_url=f"https://example.test/match/{worker_index}",
                        selection_raw=f"Mais de {2.5 + worker_index}",
                        line=2.5 + worker_index,
                    )
                ]
            ),
            Path(ledger_file),
        )
        result_queue.put(("ok", worker_index))
    except BaseException as exc:
        result_queue.put(("error", worker_index, repr(exc)))


class LedgerPortfolioGateTest(unittest.TestCase):
    def test_direct_gate_blocks_cross_config_duplicate_open_pick(self) -> None:
        existing = pd.DataFrame([official_pick(bet_id="existing", run_id="run_a", config_name="legacy_v2")])
        candidate = official_pick(bet_id="new", run_id="run_b", config_name="champion_strict")

        gate = check_against_open_ledger(candidate, existing)

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["reason"], "LEDGER_DUPLICATE_OPEN_PICK")
        self.assertEqual(gate["related_bet_id"], "existing")

    def test_direct_gate_blocks_opposite_side_same_event(self) -> None:
        existing = pd.DataFrame([official_pick(bet_id="existing", side="over", selection_raw="Mais de 2.5")])
        candidate = official_pick(bet_id="new", side="under", selection_raw="Menos de 2.5")

        gate = check_against_open_ledger(candidate, existing)

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["reason"], "LEDGER_CONTRADICTORY_OPEN_PICK")

    def test_append_to_official_like_ledger_persists_blocked_candidate_without_appending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "bets_ledger.csv"
            with patch("vcbet.core.ledger_portfolio_gate.DEFAULT_LEDGER_FILE", ledger_file):
                append_new_picks_to_ledger(pd.DataFrame([official_pick(bet_id="existing")]), ledger_file)
                append_new_picks_to_ledger(
                    pd.DataFrame([official_pick(bet_id="new", run_id="other_run", config_name="other_config")]),
                    ledger_file,
                )

            ledger = load_ledger(ledger_file)
            blocked_file = ledger_file.parent / "ledger_portfolio_blocked.csv"
            blocked = pd.read_csv(blocked_file, sep=";")

            self.assertEqual(len(ledger), 1)
            self.assertEqual(len(blocked), 1)
            self.assertEqual(blocked.loc[0, "ledger_portfolio_gate_reason"], "LEDGER_DUPLICATE_OPEN_PICK")
            self.assertEqual(blocked.loc[0, "ledger_portfolio_related_bet_id"], "existing")

    def test_concurrent_appends_are_serialized_without_losing_rows(self) -> None:
        if "fork" not in multiprocessing.get_all_start_methods():
            self.skipTest("fork multiprocessing is required for this ledger lock test")

        with tempfile.TemporaryDirectory() as tmp:
            ledger_file = Path(tmp) / "bets_ledger.csv"
            ctx = multiprocessing.get_context("fork")
            worker_count = 6
            barrier = ctx.Barrier(worker_count)
            result_queue = ctx.Queue()
            processes = [
                ctx.Process(target=append_unique_pick_worker, args=(str(ledger_file), index, barrier, result_queue))
                for index in range(worker_count)
            ]

            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                    self.fail("concurrent ledger append worker did not finish")

            results = []
            for _ in range(worker_count):
                try:
                    results.append(result_queue.get(timeout=5))
                except queue.Empty:
                    self.fail("missing result from concurrent ledger append worker")

            errors = [result for result in results if result[0] != "ok"]
            self.assertEqual(errors, [])
            self.assertEqual([process.exitcode for process in processes], [0] * worker_count)

            ledger = load_ledger(ledger_file)
            self.assertEqual(len(ledger), worker_count)
            self.assertEqual(
                sorted(ledger["bet_id"].astype(str).tolist()),
                [f"concurrent_{index}" for index in range(worker_count)],
            )


if __name__ == "__main__":
    unittest.main()
