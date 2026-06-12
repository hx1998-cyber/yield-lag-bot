"""Reject stale normalized market events."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from yield_lag_bot.models.market_event import MarketEvent


class StaleDataError(RuntimeError):
    pass


class StaleDataGuard:
    def __init__(self, *, stale_data_ms: int = 500) -> None:
        self.stale_data_ms = Decimal(stale_data_ms)

    def check(self, event: MarketEvent, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        age_ms = Decimal(str((now - event.receive_ts).total_seconds() * 1000))
        if age_ms > self.stale_data_ms:
            raise StaleDataError(
                f"stale event rejected: venue={event.venue} symbol={event.symbol} age_ms={age_ms}"
            )
