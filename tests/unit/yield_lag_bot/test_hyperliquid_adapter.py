from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from yield_lag_bot.data.hyperliquid_adapter import (
    HyperliquidAdapter,
    normalize_hyperliquid_bbo,
    normalize_hyperliquid_message,
    normalize_hyperliquid_trade,
)


def test_hyperliquid_trades_normalization() -> None:
    receive_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    event = normalize_hyperliquid_trade(
        {
            "coin": "BTC",
            "side": "B",
            "px": "65000.5",
            "sz": "0.01",
            "time": 1_700_000_000_000,
            "hash": "0xabc",
            "tid": 12,
        },
        receive_ts=receive_ts,
    )

    assert event.venue == "hyperliquid"
    assert event.symbol == "BTC"
    assert event.instrument_type == "crypto_perp"
    assert event.exchange_ts == datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=timezone.utc)
    assert event.receive_ts == receive_ts
    assert event.process_ts is not None
    assert event.last_price == Decimal("65000.5")
    assert event.sequence_id == 12
    assert event.raw_payload == {
        "channel": "trades",
        "trade": {
            "coin": "BTC",
            "side": "B",
            "px": "65000.5",
            "sz": "0.01",
            "time": 1_700_000_000_000,
            "hash": "0xabc",
            "tid": 12,
        },
    }


def test_hyperliquid_batch_trades_emit_compact_individual_payloads() -> None:
    receive_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

    events = normalize_hyperliquid_message(
        {
            "channel": "trades",
            "data": [
                {"coin": "BTC", "px": "1", "sz": "1", "time": 1_700_000_000_000, "tid": 101},
                {"coin": "BTC", "px": "2", "sz": "1", "time": 1_700_000_000_500, "tid": 102},
            ],
        },
        receive_ts=receive_ts,
    )

    assert len(events) == 2
    assert events[0].sequence_id == 101
    assert events[0].exchange_ts == datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=timezone.utc)
    assert events[0].raw_payload == {
        "channel": "trades",
        "trade": {"coin": "BTC", "px": "1", "sz": "1", "time": 1_700_000_000_000, "tid": 101},
    }
    assert events[1].sequence_id == 102
    assert events[1].exchange_ts == datetime.fromtimestamp(1_700_000_000_500 / 1000, tz=timezone.utc)
    assert events[1].raw_payload == {
        "channel": "trades",
        "trade": {"coin": "BTC", "px": "2", "sz": "1", "time": 1_700_000_000_500, "tid": 102},
    }


def test_hyperliquid_bbo_normalization() -> None:
    receive_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    event = normalize_hyperliquid_bbo(
        {
            "coin": "ETH",
            "time": 1_700_000_000_500,
            "bbo": [{"px": "3500.1", "sz": "2.0"}, {"px": "3500.2", "sz": "3.0"}],
        },
        receive_ts=receive_ts,
    )

    assert event.venue == "hyperliquid"
    assert event.symbol == "ETH"
    assert event.bid_price == Decimal("3500.1")
    assert event.ask_price == Decimal("3500.2")
    assert event.bid_size == Decimal("2.0")
    assert event.ask_size == Decimal("3.0")
    assert event.mid_price == Decimal("3500.15")
    assert event.last_price is None
    assert event.process_ts is not None
    assert event.raw_payload == {
        "channel": "bbo",
        "data": {
            "coin": "ETH",
            "time": 1_700_000_000_500,
            "bbo": [{"px": "3500.1", "sz": "2.0"}, {"px": "3500.2", "sz": "3.0"}],
        },
    }


def test_hyperliquid_message_normalization_dispatches_trades_and_bbo() -> None:
    receive_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

    trades = normalize_hyperliquid_message(
        {
            "channel": "trades",
            "data": [{"coin": "BTC", "px": "1", "sz": "1", "time": 1, "tid": 1}],
        },
        receive_ts=receive_ts,
    )
    bbo = normalize_hyperliquid_message(
        {
            "channel": "bbo",
            "data": {"coin": "BTC", "time": 1, "bbo": [{"px": "1", "sz": "1"}, {"px": "2", "sz": "1"}]},
        },
        receive_ts=receive_ts,
    )

    assert len(trades) == 1
    assert len(bbo) == 1


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_hyperliquid_reconnect_backoff_logic() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.messages = [
                '{"channel":"bbo","data":{"coin":"BTC","time":1700000000000,'
                '"bbo":[{"px":"10","sz":"1"},{"px":"11","sz":"2"}]}}'
            ]

        async def __aenter__(self) -> FakeWebSocket:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def send(self, message: str) -> None:
            self.sent.append(message)

        def __aiter__(self) -> FakeWebSocket:
            return self

        async def __anext__(self) -> str:
            if not self.messages:
                raise StopAsyncIteration
            return self.messages.pop(0)

    calls = 0
    sleeps: list[float] = []

    def connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("boom")
        return FakeWebSocket()

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async def runner() -> None:
        adapter = HyperliquidAdapter(
            ["BTC"],
            reconnect_initial_delay_sec=1,
            reconnect_max_delay_sec=4,
            connect=connect,
            sleep=sleep,
        )
        async for event in adapter.events():
            assert event.symbol == "BTC"
            break

    import asyncio

    asyncio.run(runner())
    assert sleeps == [1]
    assert calls == 2
