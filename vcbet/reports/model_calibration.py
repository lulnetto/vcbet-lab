from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from vcbet.domain.contracts import BetRecord
from vcbet.ledger.repository import LedgerRepository
from vcbet.paths import DEFAULT_LEDGER_FILE


SUCCESS_STATUSES = {"win", "half_win"}
FAILURE_STATUSES = {"loss", "half_loss"}
SETTLED_STATUSES = SUCCESS_STATUSES | FAILURE_STATUSES | {"push"}


@dataclass(slots=True)
class CalibrationBucket:
    lower: float
    upper: float
    count: int
    avg_prob: float
    observed_frequency: float
    calibration_error: float


@dataclass(slots=True)
class LeagueCalibration:
    league: str
    settled_count: int
    eligible_count: int
    excluded_count: int
    buckets: tuple[CalibrationBucket, ...]


@dataclass(slots=True)
class CalibrationReport:
    min_league_settled: int
    bin_size: float
    leagues: tuple[LeagueCalibration, ...]
    insufficient_leagues: tuple[tuple[str, int], ...]


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _status_text(value) -> str:
    return str(value or "").strip().lower()


def realized_success(record: BetRecord) -> float | None:
    status = _status_text(record.final_settlement_status)
    if status in SUCCESS_STATUSES:
        return 1.0
    if status in FAILURE_STATUSES:
        return 0.0
    return None


def is_settled_calibration_record(record: BetRecord) -> bool:
    return _status_text(record.final_bet_status) == "settled" and _status_text(record.final_settlement_status) in SETTLED_STATUSES


def calibration_rows(records: Iterable[BetRecord]) -> list[tuple[str, float, float]]:
    rows: list[tuple[str, float, float]] = []
    for record in records:
        if not is_settled_calibration_record(record):
            continue
        prob = _safe_float(record.prob_model)
        outcome = realized_success(record)
        if prob is None or outcome is None or prob < 0.0 or prob > 1.0:
            continue
        rows.append((str(record.league or "unknown"), prob, outcome))
    return rows


def _bucket_bounds(prob: float, bin_size: float) -> tuple[float, float]:
    if bin_size <= 0 or bin_size > 1:
        raise ValueError("bin_size must be in the interval (0, 1]")
    index = min(int(prob / bin_size), int(1 / bin_size) - 1)
    lower = round(index * bin_size, 10)
    upper = round(min(1.0, lower + bin_size), 10)
    return lower, upper


def build_calibration_report(
    records: Iterable[BetRecord],
    *,
    min_league_settled: int = 30,
    bin_size: float = 0.10,
) -> CalibrationReport:
    record_list = list(records)
    settled_counts: dict[str, int] = {}
    for record in record_list:
        if is_settled_calibration_record(record):
            league = str(record.league or "unknown")
            settled_counts[league] = settled_counts.get(league, 0) + 1

    rows_by_league: dict[str, list[tuple[float, float]]] = {}
    for league, prob, outcome in calibration_rows(record_list):
        rows_by_league.setdefault(league, []).append((prob, outcome))

    leagues: list[LeagueCalibration] = []
    insufficient: list[tuple[str, int]] = []
    for league in sorted(set(settled_counts) | set(rows_by_league)):
        settled_count = settled_counts.get(league, 0)
        if settled_count <= min_league_settled:
            insufficient.append((league, settled_count))
            continue

        bucket_values: dict[tuple[float, float], list[tuple[float, float]]] = {}
        for prob, outcome in rows_by_league.get(league, []):
            bucket_values.setdefault(_bucket_bounds(prob, bin_size), []).append((prob, outcome))

        buckets: list[CalibrationBucket] = []
        for (lower, upper), values in sorted(bucket_values.items()):
            avg_prob = sum(prob for prob, _ in values) / len(values)
            observed = sum(outcome for _, outcome in values) / len(values)
            buckets.append(
                CalibrationBucket(
                    lower=lower,
                    upper=upper,
                    count=len(values),
                    avg_prob=round(avg_prob, 6),
                    observed_frequency=round(observed, 6),
                    calibration_error=round(observed - avg_prob, 6),
                )
            )
        eligible_count = sum(bucket.count for bucket in buckets)
        leagues.append(
            LeagueCalibration(
                league=league,
                settled_count=settled_count,
                eligible_count=eligible_count,
                excluded_count=max(0, settled_count - eligible_count),
                buckets=tuple(buckets),
            )
        )

    return CalibrationReport(
        min_league_settled=min_league_settled,
        bin_size=bin_size,
        leagues=tuple(leagues),
        insufficient_leagues=tuple(sorted(insufficient)),
    )


def load_records_from_ledger(ledger_file: str | Path = DEFAULT_LEDGER_FILE) -> list[BetRecord]:
    return LedgerRepository(ledger_file).read()


def build_report_from_ledger(
    ledger_file: str | Path = DEFAULT_LEDGER_FILE,
    *,
    min_league_settled: int = 30,
    bin_size: float = 0.10,
) -> CalibrationReport:
    return build_calibration_report(
        load_records_from_ledger(ledger_file),
        min_league_settled=min_league_settled,
        bin_size=bin_size,
    )


def format_calibration_report(report: CalibrationReport) -> str:
    lines = [
        "# Model Calibration Report",
        "",
        "This compares `prob_model` with realized non-push outcome frequency. It is not an ROI or profitability report.",
        "Half wins count as realized successes, half losses count as realized failures, and pushes/voids are excluded from bucket frequencies.",
        f"League inclusion threshold: more than {report.min_league_settled} settled records.",
        f"Probability bin size: {report.bin_size:.2f}.",
        "",
    ]
    if not report.leagues:
        lines.append("No leagues met the minimum settled sample. Calibration sample is insufficient.")
    for league in report.leagues:
        lines.extend(
            [
                f"## {league.league}",
                "",
                f"Settled records: {league.settled_count}",
                f"Eligible calibration outcomes: {league.eligible_count}",
                f"Excluded settled records: {league.excluded_count}",
                "",
            ]
        )
        if not league.buckets:
            lines.extend(["No eligible probability buckets for this league.", ""])
            continue
        lines.extend(
            [
                "| prob_bin | count | avg_prob | observed_frequency | observed_minus_avg |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for bucket in league.buckets:
            lines.append(
                f"| {bucket.lower:.2f}-{bucket.upper:.2f} | {bucket.count} | {bucket.avg_prob:.3f} | "
                f"{bucket.observed_frequency:.3f} | {bucket.calibration_error:+.3f} |"
            )
        lines.append("")

    if report.insufficient_leagues:
        lines.extend(["## Insufficient Sample", ""])
        for league, count in report.insufficient_leagues:
            lines.append(f"- {league}: settled_records={count}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
