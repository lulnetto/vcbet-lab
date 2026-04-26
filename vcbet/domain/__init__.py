"""Domain contracts for VCBet.

These dataclasses are intentionally storage- and framework-free. Adapters may
translate CSV rows, pandas records, API payloads, or collector output into these
contracts at the boundary.
"""

from __future__ import annotations

from vcbet.domain.contracts import (
    BetRecord,
    LedgerAppendResult,
    NormalizedMarket,
    OddsSnapshot,
    PricingResult,
    XGSnapshot,
)

__all__ = [
    "BetRecord",
    "LedgerAppendResult",
    "NormalizedMarket",
    "OddsSnapshot",
    "PricingResult",
    "XGSnapshot",
]
