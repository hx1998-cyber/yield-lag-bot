from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

import pytest

from yield_lag_bot.data.cme_csv_loader import load_cme_csv
from yield_lag_bot.data.recorder import export_market_ticks_csv, export_ticks_rows
from yield_lag_bot.jobs.export_ticks import build_parser


def test_csv_export_format() -> None:
    rows = [
        {
            "venue": "hyperliquid",
            "symbol": "BTC",
            "instrument_type": "crypto_perp",
            "exchange_ts": "2024-01-01T00:00:00Z",
            "receive_ts": "2024-01-01T00:00:00.001Z",
            "process_ts": "2024-01-01T00:00:00.002Z",
            "bid_price": Decimal("10"),
            "ask_price": Decimal("11"),
            "bid_size": Decimal("1"),
            "ask_size": Decimal("2"),
            "last_price": None,
            "mid_price": Decimal("10.5"),
            "sequence_id": "1",
            "raw_payload": {"channel": "bbo"},
        }
    ]

    frame = export_ticks_rows(rows)

    assert list(frame.columns) == [
        "venue",
        "symbol",
        "instrument_type",
        "exchange_ts",
        "receive_ts",
        "process_ts",
        "bid_price",
        "ask_price",
        "bid_size",
        "ask_size",
        "last_price",
        "mid_price",
        "sequence_id",
        "raw_payload",
    ]
    assert frame.loc[0, "symbol"] == "BTC"
    assert frame.loc[0, "mid_price"] == Decimal("10.5")


def test_export_ticks_parser_accepts_channel_bbo() -> None:
    args = build_parser().parse_args(
        [
            "--venue",
            "hyperliquid",
            "--symbols",
            "BTC,ETH",
            "--channel",
            "bbo",
            "--out",
            "ticks_bbo.csv",
        ]
    )

    assert args.venue == "hyperliquid"
    assert args.symbols == "BTC,ETH"
    assert args.channel == "bbo"
    assert args.start is None
    assert args.end is None
    assert args.out == "ticks_bbo.csv"


def test_export_ticks_parser_accepts_start_end() -> None:
    args = build_parser().parse_args(
        [
            "--venue",
            "hyperliquid",
            "--symbols",
            "BTC",
            "--channel",
            "bbo",
            "--start",
            "2026-06-12T18:00:00Z",
            "--end",
            "2026-06-12T19:00:00Z",
            "--out",
            "ticks_bbo.csv",
        ]
    )

    assert args.start == "2026-06-12T18:00:00Z"
    assert args.end == "2026-06-12T19:00:00Z"


@pytest.mark.asyncio
async def test_export_market_ticks_csv_without_channel_omits_channel_filter(tmp_path: Path) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.query: object | None = None
            self.params: dict[str, object] | None = None

        async def execute(self, query, params):
            self.query = query
            self.params = params
            return []

    session = FakeSession()

    await export_market_ticks_csv(
        session,  # type: ignore[arg-type]
        venue="hyperliquid",
        symbols=["BTC", "ETH"],
        out=tmp_path / "ticks.csv",
    )

    assert "raw_payload->>'channel'" not in str(session.query)
    assert "COALESCE(exchange_ts, receive_ts)" not in str(session.query)
    assert session.params == {"venue": "hyperliquid", "symbols": ["BTC", "ETH"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["bbo", "trades"])
async def test_export_market_ticks_csv_filters_by_channel(tmp_path: Path, channel: str) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.query: object | None = None
            self.params: dict[str, object] | None = None

        async def execute(self, query, params):
            self.query = query
            self.params = params
            return []

    session = FakeSession()

    await export_market_ticks_csv(
        session,  # type: ignore[arg-type]
        venue="hyperliquid",
        symbols=["BTC", "ETH"],
        channel=channel,
        out=tmp_path / f"ticks_{channel}.csv",
    )

    query_text = str(session.query)
    assert "raw_payload->>'channel' = :channel" in query_text
    assert ":channel IS NULL" not in query_text
    assert "COALESCE(exchange_ts, receive_ts)" not in query_text
    assert session.params == {
        "venue": "hyperliquid",
        "symbols": ["BTC", "ETH"],
        "channel": channel,
    }


@pytest.mark.asyncio
async def test_export_market_ticks_csv_filters_by_start_only(tmp_path: Path) -> None:
    session = FakeSession()
    start = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)

    await export_market_ticks_csv(
        session,  # type: ignore[arg-type]
        venue="hyperliquid",
        symbols=["BTC"],
        channel="bbo",
        start=start,
        out=tmp_path / "ticks_bbo.csv",
    )

    query_text = str(session.query)
    assert "COALESCE(exchange_ts, receive_ts) >= :start_ts" in query_text
    assert "COALESCE(exchange_ts, receive_ts) < :end_ts" not in query_text
    assert "IS NULL" not in query_text
    assert session.params == {
        "venue": "hyperliquid",
        "symbols": ["BTC"],
        "channel": "bbo",
        "start_ts": start,
    }


@pytest.mark.asyncio
async def test_export_market_ticks_csv_filters_by_end_only(tmp_path: Path) -> None:
    session = FakeSession()
    end = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)

    await export_market_ticks_csv(
        session,  # type: ignore[arg-type]
        venue="hyperliquid",
        symbols=["BTC"],
        channel="bbo",
        end=end,
        out=tmp_path / "ticks_bbo.csv",
    )

    query_text = str(session.query)
    assert "COALESCE(exchange_ts, receive_ts) >= :start_ts" not in query_text
    assert "COALESCE(exchange_ts, receive_ts) < :end_ts" in query_text
    assert "IS NULL" not in query_text
    assert session.params == {
        "venue": "hyperliquid",
        "symbols": ["BTC"],
        "channel": "bbo",
        "end_ts": end,
    }


@pytest.mark.asyncio
async def test_export_market_ticks_csv_filters_by_start_and_end(tmp_path: Path) -> None:
    session = FakeSession()
    start = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc)

    await export_market_ticks_csv(
        session,  # type: ignore[arg-type]
        venue="hyperliquid",
        symbols=["BTC"],
        channel="bbo",
        start=start,
        end=end,
        out=tmp_path / "ticks_bbo.csv",
    )

    query_text = str(session.query)
    assert "COALESCE(exchange_ts, receive_ts) >= :start_ts" in query_text
    assert "COALESCE(exchange_ts, receive_ts) < :end_ts" in query_text
    assert "IS NULL" not in query_text
    assert session.params == {
        "venue": "hyperliquid",
        "symbols": ["BTC"],
        "channel": "bbo",
        "start_ts": start,
        "end_ts": end,
    }


def test_cme_csv_loader(tmp_path) -> None:
    path = tmp_path / "cme.csv"
    path.write_text(
        "timestamp,symbol,bid_price,ask_price,last_price\n"
        "2024-01-01T00:00:00Z,ZN,108.10,108.12,108.11\n",
        encoding="utf-8",
    )

    events = load_cme_csv(path)

    assert len(events) == 1
    assert events[0].venue == "cme_csv"
    assert events[0].symbol == "ZN"
    assert events[0].instrument_type == "treasury_future"
    assert events[0].bid_price == Decimal("108.10")
    assert events[0].ask_price == Decimal("108.12")
    assert events[0].last_price == Decimal("108.11")


class FakeSession:
    def __init__(self) -> None:
        self.query: object | None = None
        self.params: dict[str, object] | None = None

    async def execute(self, query, params):
        self.query = query
        self.params = params
        return []
