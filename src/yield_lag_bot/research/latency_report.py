"""Latency calculations for normalized market events."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from yield_lag_bot.models.market_event import MarketEvent


@dataclass(frozen=True, slots=True)
class LatencyStat:
    venue: str
    symbol: str
    receive_delay_ms: Decimal | None
    process_delay_ms: Decimal | None


def _ms_between(start, end) -> Decimal:
    return Decimal(str((end - start).total_seconds() * 1000))


def calculate_latency(event: MarketEvent) -> LatencyStat:
    receive_delay = None
    process_delay = None
    if event.exchange_ts is not None:
        receive_delay = _ms_between(event.exchange_ts, event.receive_ts)
        if event.process_ts is not None:
            process_delay = _ms_between(event.exchange_ts, event.process_ts)
    elif event.process_ts is not None:
        process_delay = _ms_between(event.receive_ts, event.process_ts)
    return LatencyStat(
        venue=event.venue,
        symbol=event.symbol,
        receive_delay_ms=receive_delay,
        process_delay_ms=process_delay,
    )
