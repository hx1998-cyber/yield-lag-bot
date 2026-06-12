"""M1 risk manager shell."""

from __future__ import annotations

from decimal import Decimal


class RiskManager:
    def __init__(self, *, max_order_usd: Decimal, max_position_usd: Decimal) -> None:
        self.max_order_usd = max_order_usd
        self.max_position_usd = max_position_usd
