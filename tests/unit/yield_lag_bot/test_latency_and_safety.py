from __future__ import annotations

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from yield_lag_bot.execution.crypto_executor_stub import CryptoExecutorStub
from yield_lag_bot.models.market_event import MarketEvent
from yield_lag_bot.research.latency_report import calculate_latency
from yield_lag_bot.risk.stale_data_guard import StaleDataError, StaleDataGuard


def _event(*, exchange_ts: datetime, receive_ts: datetime, process_ts: datetime | None = None) -> MarketEvent:
    return MarketEvent(
        venue="binance_usdm",
        symbol="BTCUSDT",
        instrument_type="crypto_perp",
        exchange_ts=exchange_ts,
        receive_ts=receive_ts,
        process_ts=process_ts,
        bid_price=Decimal("100"),
        ask_price=Decimal("101"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
        last_price=None,
        sequence_id="1",
        raw_payload={},
    )


def test_latency_calculation_with_exchange_and_receive_timestamps() -> None:
    exchange_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    receive_ts = exchange_ts + timedelta(milliseconds=25)
    process_ts = exchange_ts + timedelta(milliseconds=40)

    stat = calculate_latency(_event(exchange_ts=exchange_ts, receive_ts=receive_ts, process_ts=process_ts))

    assert stat.receive_delay_ms == Decimal("25.0")
    assert stat.process_delay_ms == Decimal("40.0")


def test_stale_data_guard_rejects_old_events() -> None:
    receive_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    event = _event(exchange_ts=receive_ts, receive_ts=receive_ts)

    with pytest.raises(StaleDataError):
        StaleDataGuard(stale_data_ms=500).check(
            event,
            now=receive_ts + timedelta(milliseconds=501),
        )


def test_m1_cannot_place_live_orders() -> None:
    async def runner() -> None:
        await CryptoExecutorStub(live_trading=False).place_order()

    with pytest.raises(RuntimeError, match="live trading is disabled"):
        asyncio.run(runner())
