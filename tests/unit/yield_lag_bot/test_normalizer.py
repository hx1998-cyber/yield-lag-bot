from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from yield_lag_bot.data.normalizer import normalize_binance_book_ticker, normalize_bybit_orderbook


def test_normalizer_converts_binance_payload_to_market_event() -> None:
    event = normalize_binance_book_ticker(
        {
            "e": "bookTicker",
            "u": 123,
            "s": "BTCUSDT",
            "b": "65000.10",
            "B": "1.25",
            "a": "65000.20",
            "A": "2.50",
            "E": 1_700_000_000_000,
        },
        receive_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    assert event.venue == "binance_usdm"
    assert event.symbol == "BTCUSDT"
    assert event.instrument_type == "crypto_perp"
    assert event.bid_price == Decimal("65000.10")
    assert event.ask_size == Decimal("2.50")
    assert event.sequence_id == 123
    assert event.exchange_ts == datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=timezone.utc)


def test_normalizer_converts_bybit_payload_to_market_event() -> None:
    event = normalize_bybit_orderbook(
        {
            "topic": "orderbook.1.ETHUSDT",
            "ts": 1_700_000_000_500,
            "type": "snapshot",
            "data": {
                "s": "ETHUSDT",
                "b": [["3500.10", "8.0"]],
                "a": [["3500.20", "9.5"]],
                "u": 456,
            },
        },
        receive_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    assert event.venue == "bybit"
    assert event.symbol == "ETHUSDT"
    assert event.bid_price == Decimal("3500.10")
    assert event.ask_price == Decimal("3500.20")
    assert event.bid_size == Decimal("8.0")
    assert event.sequence_id == 456
