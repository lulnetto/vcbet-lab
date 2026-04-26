from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


TEMPORAL_CONTRACT_VERSION = "temporal_contract_v1"


@dataclass(frozen=True)
class SnapshotValidationResult:
    status: str
    max_snapshot_age_hours: float
    reference_time: str
    snapshots: dict[str, dict[str, Any]]
    errors: list[dict[str, Any]]

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "max_snapshot_age_hours": self.max_snapshot_age_hours,
            "reference_time": self.reference_time,
            "snapshots": self.snapshots,
            "errors": self.errors,
        }


class SnapshotValidator:
    def __init__(self, *, max_snapshot_age_hours: float):
        if max_snapshot_age_hours is None:
            raise ValueError("max_snapshot_age_hours is mandatory")
        try:
            normalized = float(max_snapshot_age_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_snapshot_age_hours must be numeric") from exc
        if normalized <= 0:
            raise ValueError("max_snapshot_age_hours must be positive")
        self.max_snapshot_age_hours = normalized

    def validate(
        self,
        *,
        decision_timestamp: str,
        odds_snapshot_time: str | None,
        xg_asof: str | None,
    ) -> SnapshotValidationResult:
        reference = pd.to_datetime(decision_timestamp, errors="coerce")
        errors: list[dict[str, Any]] = []
        if pd.isna(reference):
            errors.append(
                {
                    "code": "decision_timestamp_invalid",
                    "snapshot": "decision",
                    "message": "decision_timestamp is required for snapshot freshness validation",
                    "snapshot_time": decision_timestamp,
                }
            )
            reference = pd.Timestamp.now()

        snapshots = {
            "odds": self._validate_one("odds", odds_snapshot_time, reference, errors),
            "xg": self._validate_one("xg", xg_asof, reference, errors),
        }
        return SnapshotValidationResult(
            status="valid" if not errors else "invalid",
            max_snapshot_age_hours=self.max_snapshot_age_hours,
            reference_time=reference.strftime("%Y-%m-%d %H:%M:%S"),
            snapshots=snapshots,
            errors=errors,
        )

    def _validate_one(
        self,
        snapshot: str,
        value: str | None,
        reference: pd.Timestamp,
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if _is_missing(value):
            errors.append(
                {
                    "code": f"{snapshot}_snapshot_time_missing",
                    "snapshot": snapshot,
                    "message": f"{snapshot} snapshot metadata is missing",
                    "snapshot_time": None,
                }
            )
            return {"snapshot_time": None, "age_hours": None, "status": "missing"}

        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            errors.append(
                {
                    "code": f"{snapshot}_snapshot_time_invalid",
                    "snapshot": snapshot,
                    "message": f"{snapshot} snapshot metadata is not a valid timestamp",
                    "snapshot_time": value,
                }
            )
            return {"snapshot_time": value, "age_hours": None, "status": "invalid_timestamp"}

        age_hours = round((reference - parsed).total_seconds() / 3600.0, 4)
        if age_hours > self.max_snapshot_age_hours:
            errors.append(
                {
                    "code": f"{snapshot}_snapshot_stale",
                    "snapshot": snapshot,
                    "message": f"{snapshot} snapshot is older than max_snapshot_age_hours",
                    "snapshot_time": parsed.strftime("%Y-%m-%d %H:%M:%S"),
                    "age_hours": age_hours,
                    "max_snapshot_age_hours": self.max_snapshot_age_hours,
                }
            )
            status = "stale"
        else:
            status = "valid"
        return {
            "snapshot_time": parsed.strftime("%Y-%m-%d %H:%M:%S"),
            "age_hours": age_hours,
            "status": status,
        }


def file_md5(path: str | Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_missing(value: Any) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def latest_timestamp_from_column(df: pd.DataFrame, column: str) -> str | None:
    if column not in df.columns or df.empty:
        return None
    parsed = pd.to_datetime(df[column], errors="coerce")
    if parsed.dropna().empty:
        return None
    return parsed.max().strftime("%Y-%m-%d %H:%M:%S")


def snapshot_time_from_dataframe(df: pd.DataFrame, fallback: Any = None) -> str | None:
    for column in ("collected_at", "snapshot_time", "generated_at"):
        value = latest_timestamp_from_column(df, column)
        if value:
            return value
    if not _is_missing(fallback):
        parsed = pd.to_datetime(fallback, errors="coerce")
        if pd.notna(parsed):
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        return str(fallback)
    return None


def temporal_contract_status(*, decision_timestamp: str | None, odds_snapshot_time: str | None, xg_asof: str | None) -> str:
    if decision_timestamp and odds_snapshot_time and xg_asof:
        return "complete"
    if decision_timestamp and (odds_snapshot_time or xg_asof):
        return "partial"
    return "legacy_missing_temporal_fields"
