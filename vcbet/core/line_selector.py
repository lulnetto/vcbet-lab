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
    if not isinstance(df_candidates, pd.DataFrame):
        return _select_top_picks(df_candidates, return_meta=return_meta)

    if df_candidates.empty:
        empty = df_candidates.copy()
        empty_rejections = pd.DataFrame()
        return (empty, empty_rejections) if return_meta else empty

    selected, rejections = _select_top_picks(df_candidates.to_dict("records"), return_meta=True)
    if selected:
        selected_df = pd.DataFrame(selected)
    else:
        selected_df = pd.DataFrame(columns=df_candidates.columns)
    rejection_df = pd.DataFrame(rejections)
    return (selected_df, rejection_df) if return_meta else selected_df


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
