from __future__ import annotations

from typing import Any

from vcbet.core.selection import _line_float, _same_target, market_family


def _is_duplicate_or_near_duplicate(a: dict[str, Any], b: dict[str, Any], tolerance: float) -> bool:
    if str(a.get("match_name") or "") != str(b.get("match_name") or ""):
        return False
    if market_family(a) != market_family(b):
        return False
    if str(a.get("side") or "") != str(b.get("side") or ""):
        return False
    if not _same_target(a, b):
        return False
    line_a = _line_float(a)
    line_b = _line_float(b)
    if line_a is None or line_b is None:
        return str(a.get("selection_raw") or "").strip().casefold() == str(b.get("selection_raw") or "").strip().casefold()
    return abs(line_a - line_b) <= tolerance


def _is_contradictory_line(a: dict[str, Any], b: dict[str, Any], tolerance: float) -> bool:
    if str(a.get("match_name") or "") != str(b.get("match_name") or ""):
        return False
    family_a = market_family(a)
    if family_a != market_family(b):
        return False
    side_a = str(a.get("side") or "")
    side_b = str(b.get("side") or "")
    line_a = _line_float(a)
    line_b = _line_float(b)

    if family_a in {"goals_total", "team_goals"}:
        if side_a == side_b or not {side_a, side_b}.issubset({"over", "under"}):
            return False
        if family_a == "team_goals" and not _same_target(a, b):
            return False
        return line_a is not None and line_b is not None and abs(line_a - line_b) <= tolerance

    if family_a == "btts":
        return {side_a, side_b} == {"yes", "no"}

    if family_a == "handicap":
        return side_a != side_b

    return False
