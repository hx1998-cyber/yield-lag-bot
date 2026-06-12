from __future__ import annotations

from decimal import Decimal
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
    assert args.out == "ticks_bbo.csv"


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
    assert session.params == {
        "venue": "hyperliquid",
        "symbols": ["BTC", "ETH"],
        "channel": channel,
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
