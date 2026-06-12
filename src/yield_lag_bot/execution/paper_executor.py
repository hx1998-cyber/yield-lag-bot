"""Paper order simulator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PaperOrder:
    venue: str
    symbol: str
    side: str
    price: Decimal
    qty: Decimal
    status: str = "simulated"


class PaperExecutor:
    def __init__(self, *, paper_trading: bool = True) -> None:
        self.paper_trading = paper_trading

    def place_order(self, *, venue: str, symbol: str, side: str, price: Decimal, qty: Decimal) -> PaperOrder:
        if not self.paper_trading:
            raise RuntimeError("paper trading is disabled")
        return PaperOrder(venue=venue, symbol=symbol, side=side, price=price, qty=qty)
