from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("VCBET_PROJECT_ROOT", os.getenv("UBET_PROJECT_ROOT", PACKAGE_ROOT.parent))).resolve()
DATA_DIR = PROJECT_ROOT / "data"
CONFIGS_DIR = PROJECT_ROOT / "configs"
LEGACY_DIR = PROJECT_ROOT / "legacy"
RUNS_DIR = DATA_DIR / "runs"
REPLAYS_DIR = DATA_DIR / "replays"
HISTORY_DIR = DATA_DIR / "history"
RESULTS_DIR = DATA_DIR / "results"
SERVICE_DIR = DATA_DIR / "service"

LIGAS_FILE = PROJECT_ROOT / "ligas.json"
ALIAS_TIMES_FILE = PROJECT_ROOT / "alias_times.json"
DEFAULT_LEDGER_FILE = HISTORY_DIR / "bets_ledger.csv"
DEFAULT_RESULTS_FILE = RESULTS_DIR / "results_auto.csv"
DEFAULT_RESULTS_DEBUG_DIR = RESULTS_DIR / "_debug"
DEFAULT_OVERRIDES_FILE = RESULTS_DIR / "results_overrides.csv"


def project_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path
