# VCBet Audit File Manifest

## Objective

This file defines the minimal source/context set for an upcoming VCBet architecture audit. It identifies source, configuration, tests, docs, and operational scripts that explain system behavior without bundling runtime data, generated artifacts, logs, caches, or historical run outputs.

## Audit Scope Summary

- Total git-tracked files: 121 (120 currently present; 1 tracked path(s) deleted in the working tree).
- Total untracked relevant files, if any: 3 (`.codexignore`, `docs/audit_file_manifest.md`, `docs/context.md`).
- Total included audit files: 113.
- Total excluded files/directories: 1041 files across 326 directories/groups.
- Approximate size of included scope: 782.7 KB.
- Approximate size of excluded scope: 49.2 MB.
- Deleted tracked paths currently observed: `configs/team_registry/betano_footystats_aliases copy.csv`.

The sections below are audit inputs, not architecture conclusions. Responsibility notes are inferred from names, imports, routes, and function/class signatures only.

## Priority 0: Entry Points and Runtime Orchestration

Entry points and compatibility shims show how operators start the service, run the pipeline, and invoke package modules from legacy root-level commands.

### `.gitignore`

- Size: 195 B
- Role: Git ignore policy for runtime data, caches, local environments, and generated outputs.
- Scope hint: confirms source/runtime boundaries from Git's perspective; it is not executable project behavior.
- Tiny sample:
```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
.vscode/
.idea/
.DS_Store
Thumbs.db
*.log
*.tmp
```

### `.codexignore`

- Size: 720 B
- Role: Codex/LLM context exclusion policy for runtime data, generated artifacts, caches, and local metadata.
- Scope hint: primary packaging guide for keeping audits focused on source files.
- Tiny sample:
```gitignore
# Git / local metadata
.git/**
.codex
.codex/**
# Runtime/generated data. Include specific data samples manually only when needed.
data/**
dev_asset/**
# Data-like historical snapshots
legacy/history_snapshots/**
```

### `requirements.txt`

- Size: 565 B
- Role: support/configuration file included for architecture context.
- Tiny sample:
```text
# UBET_v2 - dependências consolidadas de runtime
# Instalação sugerida:
#   python3 -m venv .venv
#   source .venv/bin/activate
#   python -m pip install --upgrade pip
#   python -m pip install -r requirements.txt
# Depois, para o coletor com Playwright:
#   python -m playwright install chromium
# Em Linux/WSL, se necessário:
#   python -m playwright install --with-deps chromium
```

### `run_project.sh`

- Size: 7.4 KB
- Why it matters: shell entrypoint/orchestration script used to run, validate, or smoke-test VCBet.
- Shell dependency hints: PYTHON_BIN="python3"; ./run_project.sh --mode full --date 2026-04-22 [--run-id run_20260422_120000] [--json] [--debug] [--dry-run]; ./run_project.sh --mode legacy --odds-file odds_multiplas_betano_2026-04-22.csv --xg-file base_xg_stats.csv [--date 2026-04-22] [--run-id run_20260422_120000] [--debug] [--dry-run]; --python-bin   Binário do Python (default: python3); --python-bin); "$PYTHON_BIN" -m vcbet.core.pipeline_ev "${PIPELINE_ARGS[@]}"; "$PYTHON_BIN" -m vcbet.collectors.odds_collector "${ODDS_ARGS[@]}"; "$PYTHON_BIN" -m vcbet.collectors.footystats_xg_collector "${XG_ARGS[@]}"
- Tiny sample:
```bash
#!/usr/bin/env bash
set -euo pipefail
MODE="full"
RUN_ID=""
TARGET_DATE=""
ODDS_FILE=""
XG_FILE=""
ALIAS_FILE="alias_times.json"
LEDGER_FILE="data/history/bets_ledger.csv"
OUTPUT_DIR="data/runs"
```

### `run_service.py`

- Size: 265 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: vcbet.service.api, vcbet.service.settings
- Tiny sample:
```python
from __future__ import annotations
import uvicorn
from vcbet.service.api import app
from vcbet.service.settings import ServiceSettings
if __name__ == "__main__":
    settings = ServiceSettings.load()
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### `run_service.sh`

- Size: 61 B
- Why it matters: shell entrypoint/orchestration script used to run, validate, or smoke-test VCBet.
- Shell dependency hints: python3 run_service.py
- Tiny sample:
```bash
#!/usr/bin/env bash
set -euo pipefail
python3 run_service.py
```

### `config_ligas.py`

- Size: 156 B
- Domain/responsibility: Likely configuration / project paths; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.config_ligas", run_name="__main__")
```

### `correlation_rules.py`

- Size: 161 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.correlation_rules", run_name="__main__")
```

### `footystats_xg_collector.py`

- Size: 173 B
- Domain/responsibility: Likely data collection; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.collectors.footystats_xg_collector", run_name="__main__")
```

### `ledger_manager.py`

- Size: 158 B
- Domain/responsibility: Likely ledger and portfolio state; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.ledger_manager", run_name="__main__")
```

### `market_normalizer.py`

- Size: 161 B
- Domain/responsibility: Likely market normalization / thresholds; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.market_normalizer", run_name="__main__")
```

### `market_thresholds.py`

- Size: 161 B
- Domain/responsibility: Likely market normalization / thresholds; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.market_thresholds", run_name="__main__")
```

### `odds_collector.py`

- Size: 164 B
- Domain/responsibility: Likely data collection; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.collectors.odds_collector", run_name="__main__")
```

### `pick_filter.py`

- Size: 155 B
- Domain/responsibility: Likely pick policy / selection / risk; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.pick_filter", run_name="__main__")
```

### `pricing_engine.py`

- Size: 158 B
- Domain/responsibility: Likely pricing / fair odds; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.pricing_engine", run_name="__main__")
```

### `report_ledger.py`

- Size: 163 B
- Domain/responsibility: Likely ledger and portfolio state; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.settlement.report_ledger", run_name="__main__")
```

### `run_utils.py`

- Size: 153 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.run_utils", run_name="__main__")
```

### `team_matcher.py`

- Size: 156 B
- Domain/responsibility: Likely team identity / alias registry; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from runpy import run_module
if __name__ == "__main__":
    run_module("vcbet.core.team_matcher", run_name="__main__")
```

## Priority 1: Core Domain Logic

Core package modules cover valuation, matching, risk, replay, settlement, collectors, and shared paths/config behavior.

### `vcbet/__init__.py`

- Size: 0 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected

### `vcbet/collectors/__init__.py`

- Size: 0 B
- Domain/responsibility: Likely data collection; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected

### `vcbet/collectors/closing_odds_collector.py`

- Size: 9.6 KB
- Domain/responsibility: Likely data collection; classes: BetanoClosingOddsCollector; functions: split_match_name, parse_match_datetime, line_matches, is_open_like.
- Classes: BetanoClosingOddsCollector
- Functions: split_match_name, parse_match_datetime, line_matches, is_open_like, should_consider_row, market_row_matches, resolve_final_closing_odd, collect_closing_odds
- Local imports: vcbet.core.ledger_manager, vcbet.core.market_normalizer
- Tiny sample:
```python
from __future__ import annotations
import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests
```

### `vcbet/collectors/footystats_xg_collector.py`

- Size: 9.0 KB
- Domain/responsibility: Likely data collection; functions: parse_leagues_arg, extrair_dados_completos, construir_banco_dados.
- Classes: none detected
- Functions: parse_leagues_arg, extrair_dados_completos, construir_banco_dados
- Local imports: vcbet.core.config_ligas, vcbet.core.run_utils, vcbet.core.temporal_contract
- Tiny sample:
```python
import argparse
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
```

### `vcbet/collectors/odds_collector.py`

- Size: 10.7 KB
- Domain/responsibility: Likely data collection; classes: BetanoExtractor; functions: split_match_name, save_to_csv, save_to_json_tree.
- Classes: BetanoExtractor
- Functions: split_match_name, save_to_csv, save_to_json_tree
- Local imports: vcbet.core.config_ligas, vcbet.core.market_normalizer, vcbet.core.run_utils, vcbet.core.temporal_contract
- Tiny sample:
```python
import argparse
import csv
import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
```

### `vcbet/collectors/results_collector.py`

- Size: 32.7 KB
- Domain/responsibility: Likely data collection; classes: MatchTarget, MatchResult, SofascoreBrowserClient; functions: slug_text, parse_datetime, normalize_team_for_match, team_similarity_score.
- Classes: MatchTarget, MatchResult, SofascoreBrowserClient
- Functions: slug_text, parse_datetime, normalize_team_for_match, team_similarity_score, datetime_match_bonus, utc_dt_from_timestamp, format_match_datetime, format_target_datetime, load_ledger, infer_open_mask, build_targets, fetch_json, get_current_season_id, get_score_value, event_status_to_bet_status, iter_recent_events, build_candidate_from_event, match_result_for_target, save_debug_payload, _collect_results_generic, collect_results_sofascore_api, collect_results_sofascore_browser, _should_try_api_fallback, collect_results_sofascore_auto, save_results_csv, summarize, main
- Local imports: vcbet.core.config_ligas, vcbet.core.ledger_manager, vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
import argparse
import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
```

### `vcbet/core/__init__.py`

- Size: 0 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected

### `vcbet/core/config_ligas.py`

- Size: 3.6 KB
- Domain/responsibility: Likely configuration / project paths; functions: carregar_ligas, _filtrar_por_nomes, carregar_ligas_betano, carregar_ligas_footystats.
- Classes: none detected
- Functions: carregar_ligas, _filtrar_por_nomes, carregar_ligas_betano, carregar_ligas_footystats, obter_nomes_ligas_ativas, obter_meta_liga, liga_eh_caotica, obter_nomes_ligas_caoticas, obter_result_source_url, obter_sofascore_unique_tournament_id, carregar_ligas_resultados, carregar_ligas_sofascore_ids
- Local imports: vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Set
from vcbet.paths import LIGAS_FILE
ARQUIVO_LIGAS = LIGAS_FILE
def carregar_ligas(apenas_ativas: bool = True) -> List[Dict[str, Any]]:
    with open(ARQUIVO_LIGAS, "r", encoding="utf-8") as arquivo:
        ligas = json.load(arquivo)
    if apenas_ativas:
```

### `vcbet/core/correlation_rules.py`

- Size: 204 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: vcbet.core.line_selector
- Tiny sample:
```python
from __future__ import annotations
from vcbet.core.line_selector import MARKET_PRIORITY, classify_correlation, select_top_picks
__all__ = ["MARKET_PRIORITY", "classify_correlation", "select_top_picks"]
```

### `vcbet/core/decision_policy.py`

- Size: 10.4 KB
- Domain/responsibility: Likely pick policy / selection / risk; functions: _normalize_identity_part, build_bet_id, _confidence_score, _candidate_identity.
- Classes: none detected
- Functions: _normalize_identity_part, build_bet_id, _confidence_score, _candidate_identity, _rejected_candidate_payload, evaluate_pick_candidate_with_details, evaluate_pick_candidate_with_meta, evaluate_pick_candidate
- Local imports: vcbet.core.config_ligas, vcbet.core.market_thresholds, vcbet.core.risk_policy, vcbet.core.strategy_config
- Tiny sample:
```python
from __future__ import annotations
from hashlib import md5
from typing import Any
from vcbet.core.config_ligas import liga_eh_caotica
from vcbet.core.market_thresholds import (
    get_allowed_markets,
    get_confidence_caps,
    get_confidence_penalties,
    get_critical_flags,
    get_market_priority,
```

### `vcbet/core/ledger_manager.py`

- Size: 19.1 KB
- Domain/responsibility: Likely ledger and portfolio state; functions: _empty_value, normalize_ledger_schema, _norm_identity, _norm_line.
- Classes: none detected
- Functions: _empty_value, normalize_ledger_schema, _norm_identity, _norm_line, bet_identity_key, deduplicate_ledger_rows, ensure_ledger, load_ledger, save_ledger, _pick_value, _pick_to_ledger_row, _blocked_file_for_ledger, _persist_blocked_candidates, append_new_picks_to_ledger
- Local imports: vcbet.core.ledger_portfolio_gate, vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
from pathlib import Path
from typing import Iterable
import pandas as pd
from vcbet.core.ledger_portfolio_gate import check_against_open_ledger, is_official_ledger_path
from vcbet.paths import DEFAULT_LEDGER_FILE
LEDGER_SCHEMA_VERSION = "phase11_csv_v1"
LEDGER_COLUMNS = [
    "bet_id",
    "ledger_schema_version",
```

### `vcbet/core/ledger_portfolio_gate.py`

- Size: 5.8 KB
- Domain/responsibility: Likely ledger and portfolio state; functions: is_official_ledger_path, _clean, _line_float, _same_event.
- Classes: none detected
- Functions: is_official_ledger_path, _clean, _line_float, _same_event, _same_target, _same_or_near_line, _is_open_entry, _is_contradictory, check_against_open_ledger
- Local imports: vcbet.core.line_selector, vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd
from vcbet.core.line_selector import market_family
from vcbet.paths import DEFAULT_LEDGER_FILE
OFFICIAL_LEDGER_REASONS = {
    "duplicate": "LEDGER_DUPLICATE_OPEN_PICK",
    "correlated": "LEDGER_CORRELATED_OPEN_PICK",
    "contradictory": "LEDGER_CONTRADICTORY_OPEN_PICK",
```

### `vcbet/core/line_selector.py`

- Size: 21.5 KB
- Domain/responsibility: Likely pick policy / selection / risk; functions: _append_flag, _candidate_family_key, market_family, _candidate_to_rejection.
- Classes: none detected
- Functions: _append_flag, _candidate_family_key, market_family, _candidate_to_rejection, _line_float, _same_target, _is_duplicate_or_near_duplicate, _is_contradictory_line, _exposure_rejection, _record_exposure, _apply_asian_total_line_ladder, classify_correlation, select_top_picks
- Local imports: vcbet.core.strategy_config
- Tiny sample:
```python
from __future__ import annotations
from typing import Any
import pandas as pd
from vcbet.core.strategy_config import get_runtime_config
MARKET_PRIORITY = {
    "total_goals": 1,
    "asian_total": 2,
    "asian_handicap": 3,
    "btts": 4,
    "team_total": 5,
```

### `vcbet/core/market_normalizer.py`

- Size: 9.1 KB
- Domain/responsibility: Likely market normalization / thresholds; functions: slug_text, parse_numeric_line, parse_numeric_line_suffix, compare_team_name.
- Classes: none detected
- Functions: slug_text, parse_numeric_line, parse_numeric_line_suffix, compare_team_name, _scope_terms, detect_market_scope, detect_market_scope_status, normalize_market_entry, normalize_odds_dataframe
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
import re
import unicodedata
from typing import Any, Dict
import pandas as pd
IGNORED_MARKET_TERMS = (
    "alternativas",
)
FIRST_HALF_TERMS = (
    "1 tempo",
```

### `vcbet/core/market_thresholds.py`

- Size: 789 B
- Domain/responsibility: Likely market normalization / thresholds; functions: get_market_threshold, get_primary_markets, get_allowed_markets, get_market_priority.
- Classes: none detected
- Functions: get_market_threshold, get_primary_markets, get_allowed_markets, get_market_priority, get_critical_flags, get_confidence_caps, get_confidence_penalties
- Local imports: vcbet.core.strategy_config
- Tiny sample:
```python
from __future__ import annotations
from vcbet.core.strategy_config import MarketThreshold, get_runtime_config
def get_market_threshold(market_type: str) -> MarketThreshold:
    return get_runtime_config().markets[market_type]
def get_primary_markets() -> set[str]:
    return get_runtime_config().primary_markets
def get_allowed_markets() -> set[str]:
    return get_runtime_config().allowed_markets
def get_market_priority() -> dict[str, int]:
    return get_runtime_config().market_priority
```

### `vcbet/core/pick_features.py`

- Size: 2.9 KB
- Domain/responsibility: Likely pick policy / selection / risk; functions: _display_selection, build_candidate_row.
- Classes: none detected
- Functions: _display_selection, build_candidate_row
- Local imports: vcbet.core.pricing_engine, vcbet.core.risk_policy
- Tiny sample:
```python
from __future__ import annotations
import pandas as pd
from vcbet.core.pricing_engine import effective_model_probability, expected_value_decimal, fair_odd_from_probs
from vcbet.core.risk_policy import is_xg_fallback
def _display_selection(row: pd.Series) -> str:
    """Seleção legível e identificável para relatórios, comparison e ledger."""
    selection = str(row.get("selection_raw", "")).strip()
    if str(row.get("market_type", "")).strip() == "team_total":
        team = str(row.get("target_team_name", "")).strip()
        if team and team.lower() not in {"nan", "none", "<na>", "geral"}:
```

### `vcbet/core/pick_filter.py`

- Size: 518 B
- Domain/responsibility: Likely pick policy / selection / risk; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: vcbet.core.decision_policy, vcbet.core.risk_policy
- Tiny sample:
```python
from __future__ import annotations
from vcbet.core.decision_policy import (
    build_bet_id,
    evaluate_pick_candidate,
    evaluate_pick_candidate_with_details,
    evaluate_pick_candidate_with_meta,
)
from vcbet.core.risk_policy import assess_risk_flags, is_xg_fallback, safety_gate_flags
__all__ = [
    "assess_risk_flags",
```

### `vcbet/core/pipeline_ev.py`

- Size: 32.3 KB
- Domain/responsibility: Likely support / package structure; functions: carregar_snapshot_odds, carregar_snapshot_xg, to_sorted_dict, processar_pipeline.
- Classes: none detected
- Functions: carregar_snapshot_odds, carregar_snapshot_xg, to_sorted_dict, processar_pipeline
- Local imports: vcbet.core.config_ligas, vcbet.core.decision_policy, vcbet.core.ledger_manager, vcbet.core.line_selector, vcbet.core.market_normalizer, vcbet.core.pick_features, vcbet.core.pricing_engine, vcbet.core.run_utils, vcbet.core.strategy_config, vcbet.core.team_matcher, vcbet.core.temporal_contract
- Tiny sample:
```python
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import pandas as pd
from vcbet.core.config_ligas import obter_nomes_ligas_ativas
from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.line_selector import select_top_picks
from vcbet.core.market_normalizer import normalize_odds_dataframe
from vcbet.core.pick_features import build_candidate_row
```

### `vcbet/core/pricing_engine.py`

- Size: 7.5 KB
- Domain/responsibility: Likely pricing / fair odds; functions: calculate_lambdas, expected_value_decimal, _outcome_prob, effective_model_probability.
- Classes: none detected
- Functions: calculate_lambdas, expected_value_decimal, _outcome_prob, effective_model_probability, fair_profit_loss_ratio_from_probs, fair_odd_from_probs, _univariate_probs, _settle_single_ah_component, _split_asian_line, _combine_component_results, _asian_handicap_probs, price_market_selection
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
import math
from typing import Any
from scipy.stats import poisson
def calculate_lambdas(xg_home: float, xga_home: float, xg_away: float, xga_away: float) -> dict[str, float]:
    lambda_home = max((float(xg_home) + float(xga_away)) / 2, 0.01)
    lambda_away = max((float(xg_away) + float(xga_home)) / 2, 0.01)
    return {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
```

### `vcbet/core/risk_policy.py`

- Size: 3.3 KB
- Domain/responsibility: Likely pick policy / selection / risk; functions: is_xg_fallback, _line_extreme, assess_risk_flags, safety_gate_flags.
- Classes: none detected
- Functions: is_xg_fallback, _line_extreme, assess_risk_flags, safety_gate_flags
- Local imports: vcbet.core.config_ligas, vcbet.core.market_thresholds, vcbet.core.strategy_config
- Tiny sample:
```python
from __future__ import annotations
from typing import Any
from vcbet.core.config_ligas import liga_eh_caotica
from vcbet.core.market_thresholds import get_market_threshold
from vcbet.core.strategy_config import get_runtime_config
def is_xg_fallback(xg_row: Any) -> bool:
    try:
        return (
            float(xg_row["xg_home"]) == float(xg_row["xg"])
            and float(xg_row["xg_away"]) == float(xg_row["xg"])
```

### `vcbet/core/run_utils.py`

- Size: 2.9 KB
- Domain/responsibility: Likely support / package structure; functions: now_str, generate_run_id, resolve_target_date, get_run_dir.
- Classes: none detected
- Functions: now_str, generate_run_id, resolve_target_date, get_run_dir, ensure_run_dir, build_manifest, manifest_path, quality_report_path, save_json_file, load_json_file, save_manifest, load_manifest, update_manifest, save_quality_report
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
DEFAULT_BASE_OUTPUT_DIR = Path("data") / "runs"
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def generate_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
```

### `vcbet/core/strategy_config.py`

- Size: 10.8 KB
- Domain/responsibility: Likely configuration / project paths; classes: ConfigResolutionError, MarketThreshold, RuntimeConfig; functions: _deep_merge, _build_runtime_config, resolve_config_file, load_config_payload.
- Classes: ConfigResolutionError, MarketThreshold, RuntimeConfig
- Functions: _deep_merge, _build_runtime_config, resolve_config_file, load_config_payload, configure_runtime, get_runtime_config, list_available_configs, save_runtime_snapshot
- Local imports: vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from vcbet.paths import CONFIGS_DIR
class ConfigResolutionError(FileNotFoundError):
    pass
```

### `vcbet/core/team_matcher.py`

- Size: 7.0 KB
- Domain/responsibility: Likely team identity / alias registry; classes: TeamMatchResult, PendingAliasRow; functions: now_str, slug_text, load_alias_cache, save_alias_cache.
- Classes: TeamMatchResult, PendingAliasRow
- Functions: now_str, slug_text, load_alias_cache, save_alias_cache, canonical_candidate_name, match_team_name, write_pending_aliases
- Local imports: vcbet.core.team_registry
- Tiny sample:
```python
from __future__ import annotations
import csv
import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from thefuzz import fuzz, process
from vcbet.core.team_registry import DEFAULT_REGISTRY_FILE, registry_lookup
```

### `vcbet/core/team_registry.py`

- Size: 21.2 KB
- Domain/responsibility: Likely team identity / alias registry; classes: BetanoTeam, RegistryAlias, ReviewAlias; functions: _looks_like_team_name, extract_betano_team_id, _is_betano_team_href, is_valid_betano_team_identity.
- Classes: BetanoTeam, RegistryAlias, ReviewAlias, MatchCandidate, BetanoParseResult, BetanoPhaseResult, BetanoStandingsParser
- Functions: _looks_like_team_name, extract_betano_team_id, _is_betano_team_href, is_valid_betano_team_identity, dedupe_betano_teams, duplicate_betano_entries, strip_accents, normalize_team_name, important_tokens, score_team_match, rank_candidates, ambiguity_reason, build_registry_matches, parse_betano_standings_html, parse_betano_standings_html_with_diagnostics, parse_betano_phase_standings_json, read_registry, registry_lookup, registry_alias_key, write_registry_aliases, write_review_aliases
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
import csv
import html.parser
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
```

### `vcbet/core/temporal_contract.py`

- Size: 1.6 KB
- Domain/responsibility: Likely support / package structure; functions: file_md5, _is_missing, latest_timestamp_from_column, snapshot_time_from_dataframe.
- Classes: none detected
- Functions: file_md5, _is_missing, latest_timestamp_from_column, snapshot_time_from_dataframe, temporal_contract_status
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
import pandas as pd
TEMPORAL_CONTRACT_VERSION = "temporal_contract_v1"
def file_md5(path: str | Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
```

### `vcbet/paths.py`

- Size: 1021 B
- Domain/responsibility: Likely configuration / project paths; functions: project_path.
- Classes: none detected
- Functions: project_path
- Local imports: none detected
- Tiny sample:
```python
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
```

### `vcbet/replay/__init__.py`

- Size: 0 B
- Domain/responsibility: Likely replay and comparison; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected

### `vcbet/replay/replay_pipeline.py`

- Size: 35.2 KB
- Domain/responsibility: Likely replay and comparison; functions: _load_json, _sorted_counter_dict, _normalize_signature, _normalize_family_signature.
- Classes: none detected
- Functions: _load_json, _sorted_counter_dict, _normalize_signature, _normalize_family_signature, _asian_total_line_drift, _compare_pick_sets, _resolve_source_run, _load_picks_csv, _load_csv_semicolon, _load_ledger_csv, _summarize_replay_ledger, _config_role, _model_result_summary, _build_config_scorecard, _build_comparison_context, _run_replay_settlement, _compact_picks_for_summary, _run_single_replay, replay_configs_for_run, main
- Local imports: vcbet.core.ledger_manager, vcbet.core.strategy_config, vcbet.core.temporal_contract, vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any
import pandas as pd
from vcbet.core.ledger_manager import normalize_ledger_schema
from vcbet.core.strategy_config import CONFIGS_DIR, ConfigResolutionError, list_available_configs, resolve_config_file
```

### `vcbet/settlement/__init__.py`

- Size: 0 B
- Domain/responsibility: Likely settlement / reporting; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected

### `vcbet/settlement/report_ledger.py`

- Size: 5.5 KB
- Domain/responsibility: Likely ledger and portfolio state; functions: _read_ledger, _split_flags, _print_block, build_report.
- Classes: none detected
- Functions: _read_ledger, _split_flags, _print_block, build_report
- Local imports: vcbet.core.ledger_manager
- Tiny sample:
```python
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from vcbet.core.ledger_manager import normalize_ledger_schema
def _read_ledger(path: str | Path) -> pd.DataFrame:
    df = normalize_ledger_schema(pd.read_csv(path, sep=';'))
    for col in [
        'stake_units', 'result_units_model', 'result_units_real', 'odd_entrada',
        'ev_percent', 'confidence_score', 'final_odd_fechamento'
```

### `vcbet/settlement/settlement_engine.py`

- Size: 17.7 KB
- Domain/responsibility: Likely settlement / reporting; functions: _prepare_ledger_dtypes, _is_missing, _safe_float, _safe_int.
- Classes: none detected
- Functions: _prepare_ledger_dtypes, _is_missing, _safe_float, _safe_int, _first_present, settle_total_like, settle_asian_handicap, settle_bet, compute_result_units, _slug_text, _parse_match_datetime, _result_row_score, _infer_auto_settlement_status, apply_results_file, apply_overrides_file, resolve_final_fields, settle_ledger
- Local imports: vcbet.core.ledger_manager, vcbet.core.run_utils, vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
import argparse
import re
import unicodedata
from pathlib import Path
import pandas as pd
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, load_ledger, save_ledger
from vcbet.core.run_utils import now_str
from vcbet.paths import DEFAULT_OVERRIDES_FILE
RESULTS_REQUIRED_COLUMNS = {"match_name", "home_goals", "away_goals"}
```

## Priority 2: Service / API / Frontend Surface

Service/API/frontend files define the local product surface, job orchestration, dashboards, static UI, and browser workflows.

### `vcbet/service/__init__.py`

- Size: 35 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
"""Camada de serviço do VCBet."""
```

### `vcbet/service/api.py`

- Size: 39.1 KB
- Domain/responsibility: Likely support / package structure; functions: _resource_key, _resolve_project_path, _read_text_csv, _write_text_csv.
- Classes: none detected
- Functions: _resource_key, _resolve_project_path, _read_text_csv, _write_text_csv, _read_csv_rows, _read_ledger_rows, _compact_pick_row, _load_alias_map, _save_alias_map, _alias_candidate_files, _normalize_alias_rows, _registry_approved_keys, _alias_file_payload, _project_rel, _read_jsonl_catalog, _catalog_source_paths, _catalog_is_stale, _refresh_catalog_if_needed, _format_date_label, _format_time_label, _run_label, _replay_label, _active_catalog_items, _safe_limit, health, get_configs, entity_configs, entity_ledgers, entity_runs, entity_replays
- Local imports: .commands, .dashboard, .job_runner, .job_store, .schemas, .settings, .team_registry_api, vcbet.core.ledger_manager, vcbet.core.strategy_config
- Route/API hints: @app.get("/health", response_model=HealthResponse); @app.get("/configs", response_model=list[ConfigInfo]); @app.get("/api/entities/configs"); @app.get("/api/entities/ledgers"); @app.get("/api/entities/runs"); @app.get("/api/entities/replays"); @app.get("/runs"); @app.get("/replays/summaries"); @app.get("/replays/summary"); @app.get("/replays/picks")
- Tiny sample:
```python
from __future__ import annotations
from datetime import datetime
import csv
import json
from pathlib import Path
import subprocess
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
```

### `vcbet/service/closing_watcher.py`

- Size: 4.8 KB
- Domain/responsibility: Likely support / package structure; functions: minutes_before_from_env, _has_value, _is_unsettled, eligible_rows.
- Classes: none detected
- Functions: minutes_before_from_env, _has_value, _is_unsettled, eligible_rows, update_closing_odds_once
- Local imports: vcbet.collectors.closing_odds_collector, vcbet.core.ledger_manager
- Tiny sample:
```python
from __future__ import annotations
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import pandas as pd
from vcbet.collectors.closing_odds_collector import BetanoClosingOddsCollector, market_row_matches, parse_match_datetime
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, load_ledger, save_ledger
CLOSING_FIELDS = [
    "closing_odd",
```

### `vcbet/service/commands.py`

- Size: 8.6 KB
- Domain/responsibility: Likely support / package structure; classes: CommandSpec; functions: _resolve, _append_if, build_analysis_command, build_closing_odds_command.
- Classes: CommandSpec
- Functions: _resolve, _append_if, build_analysis_command, build_closing_odds_command, build_results_command, build_settlement_command, build_run_catalog_command, build_replay_catalog_command, build_results_settlement_commands, build_daily_commands, build_replay_command
- Local imports: .schemas
- Tiny sample:
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .schemas import (
    AnalysisRequest,
    ClosingOddsRequest,
    DailyRunRequest,
    ReplayRunRequest,
    ResultsCollectionRequest,
    ResultsSettlementRequest,
```

### `vcbet/service/dashboard.py`

- Size: 14.2 KB
- Domain/responsibility: Likely support / package structure; functions: _safe_numeric, _read_csv_auto, load_ledger, _event_date_series.
- Classes: none detected
- Functions: _safe_numeric, _read_csv_auto, load_ledger, _event_date_series, apply_filters, _split_flags, _bucket_odds, _bucket_stake, _aggregate_performance, _recent_entries, build_dashboard_payload
- Local imports: vcbet.core.ledger_manager
- Tiny sample:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
import csv
import pandas as pd
from vcbet.core.ledger_manager import normalize_ledger_schema
SETTLED_BET_STATUSES = {"settled", "voided", "postponed"}
EVENT_DATE_PRIORITY = [
    "match_date",
    "event_date",
```

### `vcbet/service/job_runner.py`

- Size: 7.6 KB
- Domain/responsibility: Likely support / package structure; classes: ActiveProcess, ResourceBusyError, JobManager.
- Classes: ActiveProcess, ResourceBusyError, JobManager
- Functions: none detected
- Local imports: .commands, .job_store, .schemas
- Tiny sample:
```python
from __future__ import annotations
import os
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
```

### `vcbet/service/job_store.py`

- Size: 2.0 KB
- Domain/responsibility: Likely support / package structure; classes: JobStore.
- Classes: JobStore
- Functions: none detected
- Local imports: .schemas
- Tiny sample:
```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
from .schemas import JobRecord
class JobStore:
    def __init__(self, jobs_dir: Path):
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
    def _path_for(self, job_id: str) -> Path:
```

### `vcbet/service/schemas.py`

- Size: 5.8 KB
- Domain/responsibility: Likely support / package structure; classes: JobPhase, JobRecord, AnalysisRequest.
- Classes: JobPhase, JobRecord, AnalysisRequest, ClosingOddsRequest, ResultsCollectionRequest, SettlementRequest, ResultsSettlementRequest, DailyRunRequest, ReplayRunRequest, AliasApprovalItem, AliasApproveRequest, TeamRegistryAliasRequest, TeamRegistrySyncRequest, TeamRegistrySyncAllRequest, ConfigInfo, JobCreatedResponse, HealthResponse, JobListResponse
- Functions: none detected
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field
JobStatus = Literal["queued", "running", "success", "failed", "cancelled", "blocked", "interrupted"]
JobType = Literal["analysis", "closing_odds", "results_collection", "settlement", "results_settlement_cycle", "daily_run", "replay_run"]
class JobPhase(BaseModel):
    name: str
    status: JobStatus = "queued"
    started_at: datetime | None = None
```

### `vcbet/service/settings.py`

- Size: 1.1 KB
- Domain/responsibility: Likely support / package structure; classes: ServiceSettings.
- Classes: ServiceSettings
- Functions: none detected
- Local imports: vcbet.paths
- Tiny sample:
```python
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from vcbet.paths import PROJECT_ROOT, SERVICE_DIR
@dataclass(frozen=True)
class ServiceSettings:
    project_root: Path
    jobs_dir: Path
    logs_dir: Path
```

### `vcbet/service/static/css/components.css`

- Size: 5.2 KB
- Static asset type: CSS stylesheet
- Surface hint: UI styling/tokens/layout/components.
- Tiny sample:
```css
.tab-btn { background:transparent; color:var(--text); border:1px solid var(--border); padding:10px 14px; border-radius:999px; cursor:pointer; }
.tab-btn.active { background:var(--blue); border-color:var(--blue); }
.card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:18px; }
.kpi { background:var(--panel-soft); border:1px solid var(--border); border-radius:8px; padding:12px; }
.kpi .label { color:var(--muted); font-size:12px; }
.kpi .value { font-size:23px; font-weight:700; margin-top:6px; }
label { display:block; font-size:13px; color:var(--muted); margin-bottom:4px; }
input, select, textarea { width:100%; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
input[type="checkbox"] { width:auto; margin-right:6px; }
textarea { min-height:84px; resize:vertical; }
```

### `vcbet/service/static/css/layout.css`

- Size: 2.3 KB
- Static asset type: CSS stylesheet
- Surface hint: UI styling/tokens/layout/components.
- Tiny sample:
```css
.wrap { padding:20px; display:grid; gap:20px; }
.hero { display:flex; justify-content:space-between; align-items:end; gap:12px; flex-wrap:wrap; }
.hero p { margin:.35rem 0 0; color:var(--muted); }
.tabs { display:flex; gap:8px; flex-wrap:wrap; }
.tab { display:none; }
.tab.active { display:block; }
.grid { display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }
.jobs-grid { display:grid; gap:16px; grid-template-columns:minmax(320px,0.9fr) minmax(520px,1.6fr); }
.card + .card, .kpis + .grid, .grid + .card, .cockpit + .grid { margin-top:16px; }
.kpis { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); }
```

### `vcbet/service/static/css/tables.css`

- Size: 547 B
- Static asset type: CSS stylesheet
- Surface hint: UI styling/tokens/layout/components.
- Tiny sample:
```css
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { padding:10px 8px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }
th { color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--panel); }
.table-wrap { overflow:auto; max-height:420px; }
.table-wrap.tall { max-height:72vh; }
details.table-detail > summary { cursor:pointer; color:var(--muted); font-size:12px; }
details.table-detail pre { max-width:560px; max-height:260px; overflow:auto; margin:8px 0 0; font-size:12px; }
```

### `vcbet/service/static/css/tokens.css`

- Size: 475 B
- Static asset type: CSS stylesheet
- Surface hint: UI styling/tokens/layout/components.
- Tiny sample:
```css
:root {
  --bg:#0d1117; --panel:#161b22; --panel-soft:#1c232d; --border:#30363d; --text:#e6edf3; --muted:#9da7b3;
  --green:#238636; --blue:#1f6feb; --amber:#d29922; --danger:#da3633; --soft:#21262d;
}
* { box-sizing:border-box; }
body { margin:0; font-family:system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.45; }
h1, h2, h3 { margin:0; line-height:1.2; letter-spacing:0; }
h1 { font-size:28px; }
h2 { font-size:20px; }
h3 { font-size:16px; }
```

### `vcbet/service/static/index.html`

- Size: 18.3 KB
- Static asset type: HTML shell
- Surface hint: static UI shell; inspect linked CSS/JS modules and form ids during frontend audit.
- Tiny sample:
```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VCBet Control Center</title>
  <link rel=<redacted>
  <link rel="stylesheet" href="/static/css/layout.css" />
  <link rel="stylesheet" href="/static/css/components.css" />
  <link rel="stylesheet" href="/static/css/tables.css" />
```

### `vcbet/service/static/js/api.js`

- Size: 2.1 KB
- Static asset type: browser JavaScript
- Surface hint: browser-side API/state/component/screen logic.
- Tiny sample:
```javascript
function qs(params) {
  const url = new URLSearchParams();
  Object.entries(params).forEach(([k,v]) => {
    if (v === '' || v === null || v === undefined) return;
    url.set(k, v);
  });
  return url.toString();
}
async function api(path, options = {}) {
  const res = await fetch(path, options);
```

### `vcbet/service/static/js/app.js`

- Size: 1.9 KB
- Static asset type: browser JavaScript
- Surface hint: browser-side API/state/component/screen logic.
- Tiny sample:
```javascript
function bindTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });
}
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(x => x.classList.toggle('active', x.dataset.tab === tab));
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  const target = document.getElementById(`tab-${tab}`);
  if (target) target.classList.add('active');
```

### `vcbet/service/static/js/components.js`

- Size: 18.4 KB
- Static asset type: browser JavaScript
- Surface hint: browser-side API/state/component/screen logic.
- Tiny sample:
```javascript
function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
function formatLocalDateTime(value) {
  if (!value || value === 'NaT') return '';
```

### `vcbet/service/static/js/screens.js`

- Size: 47.6 KB
- Static asset type: browser JavaScript
- Surface hint: browser-side API/state/component/screen logic.
- Tiny sample:
```javascript
function renderNextAction() {
  const action = getNextAction();
  const el = document.getElementById('nextActionText');
  if (el) el.textContent = action.text;
  const btn = document.getElementById('nextActionButton');
  if (btn) {
    btn.textContent = action.button;
    btn.onclick = action.handler;
  }
}
```

### `vcbet/service/static/js/state.js`

- Size: 982 B
- Static asset type: browser JavaScript
- Surface hint: browser-side API/state/component/screen logic.
- Tiny sample:
```javascript
function initialLocalDate() {
  const date = new Date();
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
}
const state = {
  configs: [], jobs: [], dashboard: null, selectedJobId: null,
  replayRuns: [], replaySummaries: [], replaySummaryPayload: null, replayPicks: [],
  aliasFiles: [], aliasReview: null,
  teamRegistry: { pending: [], approved: [], leagues: [], pendingByLeague: {}, approvedByLeague: {}, loading: false, syncing: false, error: '', selectedLeague: '', reviewFilter: '', syncResult: null },
```

### `vcbet/service/team_registry_api.py`

- Size: 19.0 KB
- Domain/responsibility: Likely team identity / alias registry; functions: _now_str, _full_path, _read_csv, _write_csv_atomic.
- Classes: none detected
- Functions: _now_str, _full_path, _read_csv, _write_csv_atomic, _review_key, _matches_identity, _normalize_pending_row, _normalize_approved_row, registry_row_warnings, cleanup_invalid_approved_registry, load_pending_registry_reviews, load_approved_registry_aliases, _approved_duplicate, _pending_fieldnames, _approved_fieldnames, approve_registry_alias, reject_registry_alias, update_registry_pending_alias, list_registry_leagues, sync_registry_league, sync_all_registry_leagues
- Local imports: scripts.sync_team_aliases, vcbet.core.config_ligas, vcbet.core.team_registry
- Tiny sample:
```python
from __future__ import annotations
import csv
import os
from argparse import Namespace
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from scripts.sync_team_aliases import standings_url_for_league, sync_league
from vcbet.core.config_ligas import carregar_ligas
```

## Priority 3: Scripts and Operational Tools

Operational scripts validate releases, build catalogs, sync aliases, update closing odds, and maintain data artifacts.

### `scripts/__init__.py`

- Size: 0 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: none detected

### `scripts/approve_alias_review.py`

- Size: 2.7 KB
- Domain/responsibility: Likely team identity / alias registry; functions: read_rows, write_rows, main.
- Classes: none detected
- Functions: read_rows, write_rows, main
- Local imports: none detected
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
def read_rows(path: Path) -> tuple[list[dict[str, str]], str, list[str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
```

### `scripts/audit_data_artifacts.py`

- Size: 7.4 KB
- Domain/responsibility: Likely support / package structure; classes: Artifact; functions: date_from_parts, classify_history_file, classify_run_dir, classify_replay_dir.
- Classes: Artifact
- Functions: date_from_parts, classify_history_file, classify_run_dir, classify_replay_dir, classify_results_file, classify_service_file, inventory, write_report, main
- Local imports: none detected
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from data_catalog_utils import first_value, infer_mode, project_root, read_json, relpath
REPORT_PATH = Path("data/artifact_inventory_report.md")
TARGET_ROOTS = [
    Path("data/runs"),
```

### `scripts/build_replay_catalog.py`

- Size: 4.3 KB
- Domain/responsibility: Likely replay and comparison; functions: replay_dirs, comparison_summary, replay_strength, configs.
- Classes: none detected
- Functions: replay_dirs, comparison_summary, replay_strength, configs, build_record, sort_key, main
- Local imports: none detected
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from data_catalog_utils import (
    CATALOG_VERSION,
    existing_child,
    first_value,
    infer_created_at,
    infer_mode,
```

### `scripts/build_run_catalog.py`

- Size: 3.6 KB
- Domain/responsibility: Likely support / package structure; functions: run_dirs, build_record, sort_key, main.
- Classes: none detected
- Functions: run_dirs, build_record, sort_key, main
- Local imports: none detected
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from data_catalog_utils import (
    CATALOG_VERSION,
    existing_child,
    first_value,
    infer_created_at,
    infer_mode,
```

### `scripts/cleanup_data_artifacts.py`

- Size: 4.3 KB
- Domain/responsibility: Likely support / package structure; classes: Action; functions: is_inside_data, selected_actions, assert_safe, apply_action.
- Classes: Action
- Functions: is_inside_data, selected_actions, assert_safe, apply_action, main
- Local imports: none detected
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from audit_data_artifacts import PROTECTED, inventory
from data_catalog_utils import project_root, relpath
ARCHIVE_ROOT = Path("data/_archive/pre_cycle7_cleanup")
@dataclass(frozen=True)
```

### `scripts/data_catalog_utils.py`

- Size: 4.5 KB
- Domain/responsibility: Likely support / package structure; functions: project_root, relpath, path_from_manifest, read_json.
- Classes: none detected
- Functions: project_root, relpath, path_from_manifest, read_json, manifest_quality, first_value, infer_target_date, infer_created_at, infer_mode, existing_child, source_run_dir_from_ref, jsonl_is_valid
- Local imports: none detected
- Tiny sample:
```python
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
CATALOG_VERSION = 1
OFFICIAL_LEDGER = "data/history/bets_ledger.csv"
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]
def relpath(path: Path | str, root: Path | None = None) -> str | None:
```

### `scripts/dedupe_ledger.py`

- Size: 1.1 KB
- Domain/responsibility: Likely ledger and portfolio state; functions: main.
- Classes: none detected
- Functions: main
- Local imports: vcbet.core.ledger_manager
- Tiny sample:
```python
from __future__ import annotations
import argparse
from pathlib import Path
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE, deduplicate_ledger_rows, load_ledger, save_ledger
def main() -> None:
    parser = argparse.ArgumentParser(description="Remove entradas duplicadas do bets_ledger usando identidade estável de aposta.")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE))
    parser.add_argument("--backup", action="store_true", default=True, help="gera backup .bak antes de salvar")
    parser.add_argument("--no-backup", dest="backup", action="store_false")
    args = parser.parse_args()
```

### `scripts/run_project.sh`

- Size: 7.4 KB
- Why it matters: shell entrypoint/orchestration script used to run, validate, or smoke-test VCBet.
- Shell dependency hints: PYTHON_BIN="python3"; ./run_project.sh --mode full --date 2026-04-22 [--run-id run_20260422_120000] [--json] [--debug] [--dry-run]; ./run_project.sh --mode legacy --odds-file odds_multiplas_betano_2026-04-22.csv --xg-file base_xg_stats.csv [--date 2026-04-22] [--run-id run_20260422_120000] [--debug] [--dry-run]; --python-bin   Binário do Python (default: python3); --python-bin); "$PYTHON_BIN" -m vcbet.core.pipeline_ev "${PIPELINE_ARGS[@]}"; "$PYTHON_BIN" -m vcbet.collectors.odds_collector "${ODDS_ARGS[@]}"; "$PYTHON_BIN" -m vcbet.collectors.footystats_xg_collector "${XG_ARGS[@]}"
- Tiny sample:
```bash
#!/usr/bin/env bash
set -euo pipefail
MODE="full"
RUN_ID=""
TARGET_DATE=""
ODDS_FILE=""
XG_FILE=""
ALIAS_FILE="alias_times.json"
LEDGER_FILE="data/history/bets_ledger.csv"
OUTPUT_DIR="data/runs"
```

### `scripts/run_service.py`

- Size: 265 B
- Domain/responsibility: Likely support / package structure; mostly constants/package wiring.
- Classes: none detected
- Functions: none detected
- Local imports: vcbet.service.api, vcbet.service.settings
- Tiny sample:
```python
from __future__ import annotations
import uvicorn
from vcbet.service.api import app
from vcbet.service.settings import ServiceSettings
if __name__ == "__main__":
    settings = ServiceSettings.load()
    uvicorn.run(app, host=settings.host, port=settings.port)
```

### `scripts/run_service.sh`

- Size: 61 B
- Why it matters: shell entrypoint/orchestration script used to run, validate, or smoke-test VCBet.
- Shell dependency hints: python3 run_service.py
- Tiny sample:
```bash
#!/usr/bin/env bash
set -euo pipefail
python3 run_service.py
```

### `scripts/smoke_ui.sh`

- Size: 3.5 KB
- Why it matters: shell entrypoint/orchestration script used to run, validate, or smoke-test VCBet.
- Shell dependency hints: CONDA_BIN="${CONDA_BIN:-/home/otten/miniforge3/bin/conda}"; curl_ok() {; curl -fsS -o /dev/null "$1"; curl_ok "$BASE_URL$path"; local conda_root conda_python; conda_root="$(cd "$(dirname "$CONDA_BIN")/.." && pwd)"; conda_python="$conda_root/envs/$CONDA_ENV/bin/python"; if [[ -x "$conda_python" ]]; then
- Tiny sample:
```bash
#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-/home/otten/miniforge3/bin/conda}"
CONDA_ENV="${CONDA_ENV:-ubet}"
PYTHON_BIN="${PYTHON_BIN:-}"
BASE_URL="${VCBET_SMOKE_BASE_URL:-http://127.0.0.1:8011}"
SMOKE_HOST_PORT="${BASE_URL#http://}"
SMOKE_HOST_PORT="${SMOKE_HOST_PORT#https://}"
SMOKE_HOST="${SMOKE_HOST_PORT%%:*}"
```

### `scripts/sync_team_aliases.py`

- Size: 30.0 KB
- Domain/responsibility: Likely team identity / alias registry; classes: PhaseDiscoveryError; functions: project_root, standings_url_for_league, phase_standings_url, league_slug.
- Classes: PhaseDiscoveryError
- Functions: project_root, standings_url_for_league, phase_standings_url, league_slug, is_relevant_betano_url, extract_phase_params, phase_candidates_from_text, write_debug_artifact, load_phase_cache, save_phase_cache, cache_entry_is_valid, validate_phase_candidate, discover_phase_with_playwright, load_betano_teams_from_phase_api, fetch_html, fetch_json, league_id_from_url, latest_xg_snapshot, load_footystats_teams, load_betano_teams, coverage_status, coverage_diagnostics, sync_league, parse_args, main
- Local imports: vcbet.core.config_ligas, vcbet.core.team_registry
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
```

### `scripts/update_closing_odds.py`

- Size: 1.3 KB
- Domain/responsibility: Likely support / package structure; functions: main.
- Classes: none detected
- Functions: main
- Local imports: vcbet.core.ledger_manager, vcbet.service.closing_watcher
- Tiny sample:
```python
#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from vcbet.core.ledger_manager import DEFAULT_LEDGER_FILE
from vcbet.service.closing_watcher import update_closing_odds_once
def main() -> int:
    parser = argparse.ArgumentParser(description="Atualiza closing odds em campos dedicados usando event_url.")
    parser.add_argument("--ledger-file", default=str(DEFAULT_LEDGER_FILE))
    parser.add_argument("--window-minutes", type=int, default=None, help="Minutos antes do kickoff; usa VCBET_CLOSING_ODDS_MINUTES_BEFORE ou 60 se omitido.")
```

### `scripts/validate_release.sh`

- Size: 3.4 KB
- Why it matters: shell entrypoint/orchestration script used to run, validate, or smoke-test VCBet.
- Shell dependency hints: CONDA_BIN="${CONDA_BIN:-/home/otten/miniforge3/bin/conda}"; run_python() {; "$CONDA_BIN" run -n "$CONDA_ENV" python "$@"; run_python -m unittest discover -s tests -p 'test_*.py'; bash run_project.sh --help >/dev/null; fake_python="$GATE_TMP/fake_python.sh"; cat > "$fake_python" <<SH; vcbet.collectors.odds_collector)
- Tiny sample:
```bash
#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-/home/otten/miniforge3/bin/conda}"
CONDA_ENV="${CONDA_ENV:-ubet}"
GATE_TMP="$(mktemp -d)"
trap 'rm -rf "$GATE_TMP"' EXIT
run_python() {
  "$CONDA_BIN" run -n "$CONDA_ENV" python "$@"
}
```

## Priority 4: Configs Required for Understanding Behavior

Configuration files explain strategy presets, league metadata, legacy aliases, and approved/quarantine team registry mappings.

### `alias_times.json`

- Size: 2.1 KB
- Config/data role: JSON configuration or structured project metadata.
- Top-level keys: AC Monza, AFC Bournemouth, AS Bari, Atlanta United FC, Atlético de Madrid, Austin FC, Barcelona, Birmingham, Blackburn Rovers, Burnley, Bétis, Celta de Vigo, Charlotte FC, Charlton, Colorado Rapids, Columbus Crew SC, D.C. United, Eintracht Braunschweig, Elche, FC Cincinnati, FC Dallas, Fortuna Dusseldorf, Getafe CF, Houston Dynamo FC, Inter Miami CF
- Structural summary: AC Monza: str; AFC Bournemouth: str; AS Bari: str; Atlanta United FC: str; Atlético de Madrid: str; Austin FC: str; Barcelona: str; Birmingham: str
- Tiny sample:
```json
{
  "AC Monza": "SS Monza 1912",
  "AFC Bournemouth": "AFC Bournemouth",
  "AS Bari": "FC Bari 1908",
  "Atlanta United FC": "Atlanta United FC",
  "Atlético de Madrid": "Club Atlético de Madrid",
  "Austin FC": "Austin FC",
  "Barcelona": "FC Barcelona",
  "Birmingham": "Birmingham City FC",
  "Blackburn Rovers": "Blackburn Rovers FC",
```

### `configs/champion_strict.json`

- Size: 177 B
- Config/data role: JSON configuration or structured project metadata.
- Top-level keys: metadata
- Structural summary: metadata: object(3)
- Tiny sample:
```json
{
  "metadata": {
    "name": "champion_strict",
    "label": "Champion Strict",
    "description": "Configuração atual, mais restritiva e focada em controle de risco."
  }
}
```

### `configs/intermediate_balanced.json`

- Size: 1.6 KB
- Config/data role: JSON configuration or structured project metadata.
- Top-level keys: metadata, markets, rules, confidence_caps
- Structural summary: metadata: object(3); markets: object(5); rules: object(2); confidence_caps: object(3)
- Tiny sample:
```json
{
  "metadata": {
    "name": "intermediate_balanced",
    "label": "Intermediate Balanced",
    "description": "Meio-termo entre o champion strict e um baseline mais permissivo."
  },
  "markets": {
    "total_goals": {
      "odd_min": 1.62,
      "standard_max": 2.70,
```

### `configs/legacy_recovered.json`

- Size: 2.1 KB
- Config/data role: JSON configuration or structured project metadata.
- Top-level keys: metadata, markets, rules, confidence_caps, confidence_penalties
- Structural summary: metadata: object(3); markets: object(5); rules: object(2); confidence_caps: object(8); confidence_penalties: object(14)
- Tiny sample:
```json
{
  "metadata": {
    "name": "legacy_recovered",
    "label": "Legacy Recovered",
    "description": "Baseline permissiva reconstruída a partir dos snapshots de 22/04, priorizando recuperar o comportamento antigo."
  },
  "markets": {
    "total_goals": {
      "odd_min": 1.55,
      "standard_max": 2.90,
```

### `configs/legacy_v2.json`

- Size: 1.7 KB
- Config/data role: JSON configuration or structured project metadata.
- Top-level keys: metadata, market_priority, markets, rules, confidence_caps
- Structural summary: metadata: object(3); market_priority: object(5); markets: object(3); rules: object(3); confidence_caps: object(4)
- Tiny sample:
```json
{
  "metadata": {
    "name": "legacy_v2",
    "label": "Legacy v2",
    "description": "Preset baseado no intermediate_balanced, mas com preferência por asian_total e ladder de linhas para aproximar a carteira lucrativa de 22/04."
  },
  "market_priority": {
    "asian_total": 1,
    "total_goals": 2,
    "asian_handicap": 3,
```

### `configs/team_registry/betano_footystats_aliases.csv`

- Size: 67.7 KB
- Config/data role: CSV configuration/reference table.
- Header: league;betano_name;betano_team_id;betano_url;footystats_name;match_status;match_confidence;match_method;approved_at;source
- Row count: 248
- First 3 rows:
```csv
2. Bundesliga;1. FC Kaiserslautern;106827;https://www.betano.bet.br/sport/futebol/competicoes/alemanha/217/1-fc-kaiserslautern/106827-t/;1. FC Kaiserslautern;MATCH_REGISTRY_APPROVED;1.0000;registry_auto_strict;2026-04-25 10:04:00;https://www.betano.bet.br/sport/futebol/alemanha/2-bundesliga/217/?bt=standings
2. Bundesliga;1. FC Magdeburg;107238;https://www.betano.bet.br/sport/futebol/competicoes/alemanha/217/1-fc-magdeburg/107238-t/;1. FC Magdeburg;MATCH_REGISTRY_APPROVED;1.0000;registry_auto_strict;2026-04-25 10:04:00;https://www.betano.bet.br/sport/futebol/alemanha/2-bundesliga/217/?bt=standings
2. Bundesliga;1. FC Nurnberg;107658;https://www.betano.bet.br/sport/futebol/competicoes/alemanha/217/1-fc-nurnberg/107658-t/;1. FC Nürnberg;MATCH_REGISTRY_APPROVED;1.0000;registry_auto_strict;2026-04-25 10:04:00;https://www.betano.bet.br/sport/futebol/alemanha/2-bundesliga/217/?bt=standings
```

### `configs/team_registry/betano_footystats_aliases_quarantine.csv`

- Size: 15.0 KB
- Config/data role: CSV configuration/reference table.
- Header: league;betano_name;betano_team_id;betano_url;footystats_name;match_status;match_confidence;match_method;approved_at;source;quarantine_reason;quarantined_at
- Row count: 248
- First 3 rows:
```csv
Bundesliga;Bayern de Munique;;;FC Bayern München;MATCH_REGISTRY_APPROVED;1.0000;registry_auto_strict;2026-04-25 02:13:23;patch_8_4_local_html_validation;invalid_betano_team_identity;2026-04-25
Bundesliga;Borussia Dortmund;;;BVB 09 Borussia Dortmund;MATCH_REGISTRY_APPROVED;1.0000;registry_auto_strict;2026-04-25 02:13:23;patch_8_4_local_html_validation;invalid_betano_team_identity;2026-04-25
;;;;;;;;;;invalid_betano_team_identity;2026-04-25 10:01:13
```

### `ligas.json`

- Size: 5.4 KB
- Config/data role: JSON configuration or structured project metadata.
- Top-level keys: none or non-object JSON
- Structural summary: top-level array(16); first item type: dict
- Tiny sample: omitted because this is config/data-heavy; structure above is the sample.

## Priority 5: Tests and Documentation

Tests and docs describe expected behavior and current operating contracts.

### `README.md`

- Size: 1.6 KB
- Documentation role: project guidance, operations, contracts, or architecture map.
- Tiny sample:
```markdown
# VCBet
VCBet is a personal football betting valuation and research system. It uses football data such as xG/xGA, odds snapshots, market normalization, risk rules, replay runs, and settlement outputs to identify possible value odds across markets such as asian total, total goals, team total, BTTS, and related markets.
VCBet is not a proven profitable betting engine. Treat it as a personal research and operational tool whose outputs still require review, data-quality checks, and bankroll discipline.
## Environment
Canonical environment:
- WSL/Linux
- project path: `/mnt/c/Users/Netto/Documents/VCBet`
- conda env: `ubet`
- preferred command style: `/home/otten/miniforge3/bin/conda run -n ubet <command>`
## Validate
```

### `docs/DATA_MODEL.md`

- Size: 5.3 KB
- Documentation role: project guidance, operations, contracts, or architecture map.
- Tiny sample:
```markdown
# Data Model
VCBet keeps runtime data as files under `data/`. The product source of truth remains simple and explicit: the canonical official betting ledger is `data/history/bets_ledger.csv`.
## Ledgers
- `data/history/bets_ledger.csv` is the only canonical official ledger.
- Other ledger-like files may exist for sandbox, replay, debug, rerun, or legacy development work.
- Ledger-like files outside the canonical path should be treated as non-official unless a human explicitly promotes them.
- The official ledger schema is not changed by catalog generation or cleanup tooling.
- `event_url` is optional for backward compatibility, but recommended because it enables closing odds collection.
- Official appends pass through a ledger-level portfolio gate that checks open/unsettled exposure already present in the canonical ledger. Blocked cross-run/cross-config duplicates, correlations, and contradictions are written to a review artifact instead of being appended silently.
Closing odds are stored in closing-specific fields (`closing_odd`, `closing_bookmaker`, `closing_snapshot_time`, `closing_source`, `closing_update_status`, `closing_update_error`). They must not overwrite `odd_entrada`, model odds, or other original decision fields.
```

### `docs/FRONTEND_MAP.md`

- Size: 3.5 KB
- Documentation role: project guidance, operations, contracts, or architecture map.
- Tiny sample:
```markdown
# Frontend Map
The frontend is a static UI served by the VCBet service from `vcbet/service/static/`.
It uses classic global scripts, not ES modules. Preserve global functions referenced by inline handlers in `index.html`.
## Files
- `index.html`: application shell, screen containers, tabs, forms, and script/style includes.
- `css/tokens.css`: <redacted>
- `css/layout.css`: page layout, navigation, tab structure, cockpit layout, grids, and responsive screen structure.
- `css/components.css`: cards, buttons, badges, forms, drawers, empty states, alerts, and reusable visual components.
- `css/tables.css`: table layout, wrappers, row states, and dense data presentation.
- `js/api.js`: API wrapper functions used by screens and actions.
```

### `docs/MANIFEST_CONTRACT.md`

- Size: 2.7 KB
- Documentation role: project guidance, operations, contracts, or architecture map.
- Tiny sample:
```markdown
# Manifest Contract
`run_manifest.json` already exists in current run and replay folders. Cycle 7 does not introduce a breaking manifest migration; it adds catalog builders that read existing manifests defensively.
## Compatibility Rule
Old runs must not break just because their manifest is partial. Missing fields should become `null`, safe defaults, or inferred values in catalogs. Historical manifests should be preserved as written.
## Recommended Run Manifest Fields
- `run_id`
- `target_date`
- `created_at`
- `updated_at`
- `status`
```

### `docs/OPERATIONS.md`

- Size: 5.5 KB
- Documentation role: project guidance, operations, contracts, or architecture map.
- Tiny sample:
```markdown
# Operations
VCBet is operated as a local WSL/Linux project with the `ubet` conda environment.
## Environment
Preferred command style:
` ` `bash
/home/otten/miniforge3/bin/conda run -n ubet <command>
` ` `
From the project root:
` ` `bash
cd /mnt/c/Users/Netto/Documents/VCBet
```

### `docs/PROJECT_MAP.md`

- Size: 4.8 KB
- Documentation role: project guidance, operations, contracts, or architecture map.
- Tiny sample:
```markdown
# Project Map
This map explains what each major area is for and whether it is usually source code, compatibility glue, or runtime output.
## Main Package: `vcbet/`
### `vcbet/core/`
Purpose: core valuation and decision logic, including pricing, market normalization, pick filters, portfolio/risk rules, team matching, strategy config, temporal contracts, and the daily pipeline.
Type: source code.
Edit here: yes, for valuation behavior and core domain changes.
### `vcbet/collectors/`
Purpose: data collection modules for odds, xG, closing odds, and match results.
Type: source code.
```

### `tests/test_closing_watcher.py`

- Size: 1.8 KB
- Domain/responsibility: Likely support / package structure; classes: ClosingWatcherTest; functions: official_pick.
- Classes: ClosingWatcherTest
- Functions: official_pick
- Local imports: vcbet.service.closing_watcher
- Tiny sample:
```python
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
```

### `tests/test_daily_config_selection.py`

- Size: 2.9 KB
- Domain/responsibility: Likely configuration / project paths; functions: test_daily_command_includes_selected_config_name, test_run_project_full_mode_forwards_config_name_to_pipeline.
- Classes: none detected
- Functions: test_daily_command_includes_selected_config_name, test_run_project_full_mode_forwards_config_name_to_pipeline
- Local imports: vcbet.service.commands, vcbet.service.schemas
- Tiny sample:
```python
from __future__ import annotations
import subprocess
from pathlib import Path
from vcbet.service.commands import build_daily_commands
from vcbet.service.schemas import DailyRunRequest
PROJECT_ROOT = Path(__file__).resolve().parents[1]
def test_daily_command_includes_selected_config_name() -> None:
    for config_name in ("legacy_v2", "champion_strict"):
        commands = build_daily_commands(
            PROJECT_ROOT,
```

### `tests/test_decision_architecture.py`

- Size: 7.1 KB
- Domain/responsibility: Likely pick policy / selection / risk; classes: DecisionArchitectureTest; functions: base_candidate.
- Classes: DecisionArchitectureTest
- Functions: base_candidate
- Local imports: vcbet.core.decision_policy, vcbet.core.line_selector, vcbet.core.pricing_engine, vcbet.core.risk_policy, vcbet.core.strategy_config, vcbet.service.dashboard
- Tiny sample:
```python
from __future__ import annotations
import unittest
import pandas as pd
from vcbet.core.decision_policy import evaluate_pick_candidate_with_details
from vcbet.core.line_selector import select_top_picks
from vcbet.core.pricing_engine import expected_value_decimal, price_market_selection
from vcbet.core.risk_policy import assess_risk_flags, safety_gate_flags
from vcbet.core.strategy_config import configure_runtime
from vcbet.service.dashboard import build_dashboard_payload
def base_candidate(**overrides):
```

### `tests/test_ledger_portfolio_gate.py`

- Size: 3.5 KB
- Domain/responsibility: Likely ledger and portfolio state; classes: LedgerPortfolioGateTest; functions: official_pick.
- Classes: LedgerPortfolioGateTest
- Functions: official_pick
- Local imports: vcbet.core.ledger_manager, vcbet.core.ledger_portfolio_gate
- Tiny sample:
```python
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from vcbet.core.ledger_manager import append_new_picks_to_ledger, load_ledger
from vcbet.core.ledger_portfolio_gate import check_against_open_ledger
def official_pick(**overrides) -> dict:
    payload = {
```

### `tests/test_ledger_provenance.py`

- Size: 10.3 KB
- Domain/responsibility: Likely ledger and portfolio state; classes: LedgerProvenanceTest; functions: official_pick.
- Classes: LedgerProvenanceTest
- Functions: official_pick
- Local imports: vcbet.collectors.results_collector, vcbet.core.ledger_manager, vcbet.replay.replay_pipeline, vcbet.service.dashboard, vcbet.settlement.report_ledger, vcbet.settlement.settlement_engine
- Tiny sample:
```python
from __future__ import annotations
import tempfile
import unittest
import warnings
from pathlib import Path
import pandas as pd
from vcbet.collectors.results_collector import build_targets, load_ledger as load_results_ledger
from vcbet.core.ledger_manager import append_new_picks_to_ledger, load_ledger
from vcbet.replay.replay_pipeline import _summarize_replay_ledger
from vcbet.service.dashboard import build_dashboard_payload
```

### `tests/test_market_normalizer.py`

- Size: 4.9 KB
- Domain/responsibility: Likely market normalization / thresholds; classes: MarketNormalizerTest.
- Classes: MarketNormalizerTest
- Functions: none detected
- Local imports: vcbet.core.market_normalizer
- Tiny sample:
```python
from __future__ import annotations
import math
import tempfile
import unittest
from pathlib import Path
from vcbet.core.market_normalizer import detect_market_scope, normalize_market_entry
class MarketNormalizerTest(unittest.TestCase):
    def test_primeiro_tempo_is_not_normalized_as_full_time(self) -> None:
        normalized = normalize_market_entry(
            market_raw="Total de Gols Mais/Menos - Primeiro Tempo",
```

### `tests/test_pick_safety_gates.py`

- Size: 3.3 KB
- Domain/responsibility: Likely pick policy / selection / risk; classes: PickSafetyGateTest; functions: base_candidate.
- Classes: PickSafetyGateTest
- Functions: base_candidate
- Local imports: vcbet.core.pick_filter, vcbet.core.strategy_config
- Tiny sample:
```python
from __future__ import annotations
import unittest
from vcbet.core.pick_filter import evaluate_pick_candidate_with_details
from vcbet.core.strategy_config import configure_runtime
def base_candidate(**overrides):
    payload = {
        "run_id": "run_test",
        "odds_source_run_id": "run_test",
        "xg_source_run_id": "run_test",
        "generated_at": "2026-04-24 12:00:00",
```

### `tests/test_portfolio_risk.py`

- Size: 6.9 KB
- Domain/responsibility: Likely pick policy / selection / risk; classes: PortfolioRiskTest; functions: candidate.
- Classes: PortfolioRiskTest
- Functions: candidate
- Local imports: vcbet.core.line_selector, vcbet.core.strategy_config, vcbet.service.dashboard
- Tiny sample:
```python
from __future__ import annotations
import unittest
import pandas as pd
from vcbet.core.line_selector import select_top_picks
from vcbet.core.strategy_config import configure_runtime, get_runtime_config
from vcbet.service.dashboard import build_dashboard_payload
def candidate(**overrides):
    payload = {
        "run_id": "run_test",
        "generated_at": "2026-04-24 12:00:00",
```

### `tests/test_pricing_engine.py`

- Size: 4.0 KB
- Domain/responsibility: Likely pricing / fair odds; classes: PricingEngineTest.
- Classes: PricingEngineTest
- Functions: none detected
- Local imports: vcbet.core.pricing_engine
- Tiny sample:
```python
from __future__ import annotations
import unittest
from vcbet.core.pricing_engine import (
    effective_model_probability,
    expected_value_decimal,
    fair_odd_from_probs,
    price_market_selection,
)
class PricingEngineTest(unittest.TestCase):
    def assertAlmostZero(self, value: float, places: int = 9) -> None:
```

### `tests/test_pricing_outputs.py`

- Size: 3.7 KB
- Domain/responsibility: Likely pricing / fair odds; classes: PricingOutputTest.
- Classes: PricingOutputTest
- Functions: none detected
- Local imports: vcbet.core.pick_features, vcbet.service.dashboard
- Tiny sample:
```python
from __future__ import annotations
import unittest
import pandas as pd
from vcbet.core.pick_features import build_candidate_row
from vcbet.service.dashboard import build_dashboard_payload
class PricingOutputTest(unittest.TestCase):
    def test_candidate_and_dashboard_payload_carry_corrected_pricing_fields(self) -> None:
        row = pd.Series(
            {
                "league": "Liga Teste",
```

### `tests/test_replay_comparison_scorecard.py`

- Size: 5.1 KB
- Domain/responsibility: Likely replay and comparison; classes: ReplayComparisonScorecardTest.
- Classes: ReplayComparisonScorecardTest
- Functions: none detected
- Local imports: vcbet.replay.replay_pipeline
- Tiny sample:
```python
from __future__ import annotations
import unittest
from vcbet.replay.replay_pipeline import (
    MANUAL_CONSERVATIVE_REFERENCE_CONFIG,
    MANUAL_DEFAULT_BASELINE_CONFIG,
    _build_comparison_context,
    _build_config_scorecard,
)
class ReplayComparisonScorecardTest(unittest.TestCase):
    def test_config_scorecard_exposes_replay_evidence_coherently(self) -> None:
```

### `tests/test_service_composed_workflows.py`

- Size: 2.1 KB
- Domain/responsibility: Likely support / package structure; classes: ServiceComposedWorkflowTest.
- Classes: ServiceComposedWorkflowTest
- Functions: none detected
- Local imports: vcbet.service.commands, vcbet.service.dashboard, vcbet.service.schemas
- Tiny sample:
```python
from __future__ import annotations
import unittest
from pathlib import Path
import pandas as pd
from vcbet.service.dashboard import apply_filters
from vcbet.service.commands import build_daily_commands, build_results_settlement_commands
from vcbet.service.schemas import DailyRunRequest, ResultsSettlementRequest
class ServiceComposedWorkflowTest(unittest.TestCase):
    def test_results_settlement_cycle_keeps_results_and_settlement_as_separate_phases(self) -> None:
        commands = build_results_settlement_commands(
```

### `tests/test_team_registry.py`

- Size: 9.0 KB
- Domain/responsibility: Likely team identity / alias registry; classes: TeamRegistryTest; functions: phase_payload.
- Classes: TeamRegistryTest
- Functions: phase_payload
- Local imports: scripts.sync_team_aliases, vcbet.core.team_matcher, vcbet.core.team_registry
- Tiny sample:
```python
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from vcbet.core.team_matcher import match_team_name
from vcbet.core.team_registry import (
    BetanoTeam,
    build_registry_matches,
    normalize_team_name,
    parse_betano_phase_standings_json,
```

### `tests/test_team_registry_api.py`

- Size: 18.8 KB
- Domain/responsibility: Likely team identity / alias registry; classes: TeamRegistryApiTest; functions: phase_payload.
- Classes: TeamRegistryApiTest
- Functions: phase_payload
- Local imports: scripts.sync_team_aliases, vcbet.core.risk_policy, vcbet.service.team_registry_api
- Tiny sample:
```python
from __future__ import annotations
import csv
import json
import tempfile
import unittest
from pathlib import Path
from vcbet.core.risk_policy import safety_gate_flags
from vcbet.service.team_registry_api import (
    approve_registry_alias,
    list_registry_leagues,
```

### `tests/test_temporal_contract.py`

- Size: 13.9 KB
- Domain/responsibility: Likely support / package structure; classes: TemporalContractTest.
- Classes: TemporalContractTest
- Functions: none detected
- Local imports: vcbet.core.ledger_manager, vcbet.core.pipeline_ev, vcbet.core.temporal_contract, vcbet.replay.replay_pipeline, vcbet.service.dashboard
- Tiny sample:
```python
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from vcbet.core.ledger_manager import append_new_picks_to_ledger, load_ledger
from vcbet.core.pipeline_ev import processar_pipeline
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION, snapshot_time_from_dataframe
from vcbet.replay.replay_pipeline import _resolve_source_run
```

## Suggested Audit Upload Set

Send these files as the architecture audit source set. Send `docs/audit_file_manifest.md` and `docs/context.md` as briefing documents, not as source evidence to be re-audited.

### P0: Entry Points and Runtime Orchestration
- `.gitignore`
- `.codexignore`
- `requirements.txt`
- `run_project.sh`
- `run_service.py`
- `run_service.sh`
- `config_ligas.py`
- `correlation_rules.py`
- `footystats_xg_collector.py`
- `ledger_manager.py`
- `market_normalizer.py`
- `market_thresholds.py`
- `odds_collector.py`
- `pick_filter.py`
- `pricing_engine.py`
- `report_ledger.py`
- `run_utils.py`
- `team_matcher.py`

### P1: Core Domain Logic
- `vcbet/__init__.py`
- `vcbet/collectors/__init__.py`
- `vcbet/collectors/closing_odds_collector.py`
- `vcbet/collectors/footystats_xg_collector.py`
- `vcbet/collectors/odds_collector.py`
- `vcbet/collectors/results_collector.py`
- `vcbet/core/__init__.py`
- `vcbet/core/config_ligas.py`
- `vcbet/core/correlation_rules.py`
- `vcbet/core/decision_policy.py`
- `vcbet/core/ledger_manager.py`
- `vcbet/core/ledger_portfolio_gate.py`
- `vcbet/core/line_selector.py`
- `vcbet/core/market_normalizer.py`
- `vcbet/core/market_thresholds.py`
- `vcbet/core/pick_features.py`
- `vcbet/core/pick_filter.py`
- `vcbet/core/pipeline_ev.py`
- `vcbet/core/pricing_engine.py`
- `vcbet/core/risk_policy.py`
- `vcbet/core/run_utils.py`
- `vcbet/core/strategy_config.py`
- `vcbet/core/team_matcher.py`
- `vcbet/core/team_registry.py`
- `vcbet/core/temporal_contract.py`
- `vcbet/paths.py`
- `vcbet/replay/__init__.py`
- `vcbet/replay/replay_pipeline.py`
- `vcbet/settlement/__init__.py`
- `vcbet/settlement/report_ledger.py`
- `vcbet/settlement/settlement_engine.py`

### P2: Service / API / Frontend Surface
- `vcbet/service/__init__.py`
- `vcbet/service/api.py`
- `vcbet/service/closing_watcher.py`
- `vcbet/service/commands.py`
- `vcbet/service/dashboard.py`
- `vcbet/service/job_runner.py`
- `vcbet/service/job_store.py`
- `vcbet/service/schemas.py`
- `vcbet/service/settings.py`
- `vcbet/service/static/css/components.css`
- `vcbet/service/static/css/layout.css`
- `vcbet/service/static/css/tables.css`
- `vcbet/service/static/css/tokens.css`
- `vcbet/service/static/index.html`
- `vcbet/service/static/js/api.js`
- `vcbet/service/static/js/app.js`
- `vcbet/service/static/js/components.js`
- `vcbet/service/static/js/screens.js`
- `vcbet/service/static/js/state.js`
- `vcbet/service/team_registry_api.py`

### P3: Scripts and Operational Tools
- `scripts/__init__.py`
- `scripts/approve_alias_review.py`
- `scripts/audit_data_artifacts.py`
- `scripts/build_replay_catalog.py`
- `scripts/build_run_catalog.py`
- `scripts/cleanup_data_artifacts.py`
- `scripts/data_catalog_utils.py`
- `scripts/dedupe_ledger.py`
- `scripts/run_project.sh`
- `scripts/run_service.py`
- `scripts/run_service.sh`
- `scripts/smoke_ui.sh`
- `scripts/sync_team_aliases.py`
- `scripts/update_closing_odds.py`
- `scripts/validate_release.sh`

### P4: Configs Required for Understanding Behavior
- `alias_times.json`
- `configs/champion_strict.json`
- `configs/intermediate_balanced.json`
- `configs/legacy_recovered.json`
- `configs/legacy_v2.json`
- `configs/team_registry/betano_footystats_aliases.csv`
- `configs/team_registry/betano_footystats_aliases_quarantine.csv`
- `ligas.json`

### P5: Tests and Documentation
- `README.md`
- `docs/DATA_MODEL.md`
- `docs/FRONTEND_MAP.md`
- `docs/MANIFEST_CONTRACT.md`
- `docs/OPERATIONS.md`
- `docs/PROJECT_MAP.md`
- `tests/test_closing_watcher.py`
- `tests/test_daily_config_selection.py`
- `tests/test_decision_architecture.py`
- `tests/test_ledger_portfolio_gate.py`
- `tests/test_ledger_provenance.py`
- `tests/test_market_normalizer.py`
- `tests/test_pick_safety_gates.py`
- `tests/test_portfolio_risk.py`
- `tests/test_pricing_engine.py`
- `tests/test_pricing_outputs.py`
- `tests/test_replay_comparison_scorecard.py`
- `tests/test_service_composed_workflows.py`
- `tests/test_team_registry.py`
- `tests/test_team_registry_api.py`
- `tests/test_temporal_contract.py`
