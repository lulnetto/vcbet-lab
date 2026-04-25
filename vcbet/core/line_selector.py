from __future__ import annotations

import pandas as pd

from vcbet.core.selection import (
    MARKET_PRIORITY,
    _append_flag,
    _apply_asian_total_line_ladder,
    _candidate_family_key,
    _candidate_to_rejection,
    _exposure_rejection,
    _is_contradictory_line,
    _is_duplicate_or_near_duplicate,
    _line_float,
    _record_exposure,
    _same_target,
    classify_correlation,
    market_family,
)
from vcbet.core.selection.line_selection import select_top_picks as _select_top_picks


def select_top_picks(df_candidates: pd.DataFrame, return_meta: bool = False):
    return _select_top_picks(df_candidates, return_meta=return_meta)


__all__ = [
    "MARKET_PRIORITY",
    "_append_flag",
    "_candidate_family_key",
    "market_family",
    "_candidate_to_rejection",
    "_line_float",
    "_same_target",
    "_is_duplicate_or_near_duplicate",
    "_is_contradictory_line",
    "_exposure_rejection",
    "_record_exposure",
    "_apply_asian_total_line_ladder",
    "classify_correlation",
    "select_top_picks",
]
