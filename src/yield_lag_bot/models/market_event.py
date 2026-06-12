"""Normalized market data event model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class MarketEvent:
    venue: str
    symbol: str
    instrument_type: str
    exchange_ts: datetime | None
    receive_ts: datetime
    process_ts: datetime | None
    bid_price: Decimal | None
    ask_price: Decimal | None
    bid_size: Decimal | None
    ask_size: Decimal | None
    last_price: Decimal | None
    sequence_id: str | int | None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def mid_price(self) -> Decimal | None:
        if self.bid_price is None or self.ask_price is None:
            return None
        return (self.bid_price + self.ask_price) / Decimal("2")

    def __post_init__(self) -> None:
        if self.receive_ts.tzinfo is None:
            object.__setattr__(self, "receive_ts", self.receive_ts.replace(tzinfo=timezone.utc))
        if self.exchange_ts is not None and self.exchange_ts.tzinfo is None:
            object.__setattr__(self, "exchange_ts", self.exchange_ts.replace(tzinfo=timezone.utc))
        if self.process_ts is not None and self.process_ts.tzinfo is None:
            object.__setattr__(self, "process_ts", self.process_ts.replace(tzinfo=timezone.utc))
