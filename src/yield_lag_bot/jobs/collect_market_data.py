"""Collect public market data and persist normalized ticks."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator

from baccarat.storage.postgres import PostgresClient

from yield_lag_bot.config import load_settings
from yield_lag_bot.data.binance_futures_adapter import BinanceFuturesAdapter
from yield_lag_bot.data.hyperliquid_adapter import HyperliquidAdapter
from yield_lag_bot.data.recorder import record_market_event
from yield_lag_bot.models.market_event import MarketEvent


def _parse_symbols(value: str | None, defaults: list[str]) -> list[str]:
    if value is None:
        return defaults
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


def build_adapter(venue: str, symbols: list[str]) -> AsyncIterator[MarketEvent]:
    settings = load_settings()
    if venue == "hyperliquid":
        return HyperliquidAdapter(symbols, ws_url=settings.hyperliquid_ws_url).events()
    if venue == "binance":
        return BinanceFuturesAdapter(symbols, ws_url=settings.binance_ws_url).events()
    raise ValueError(f"unsupported venue: {venue}")


async def collect(
    *,
    venue: str,
    symbols: list[str],
    duration: int | None,
) -> int:
    settings = load_settings()
    deadline = None if duration is None else asyncio.get_running_loop().time() + duration
    pg = PostgresClient.from_url(
        settings.database_url,
        pool_min_size=settings.postgres_pool_min_size,
        pool_max_size=settings.postgres_pool_max_size,
    )
    count = 0
    try:
        async for event in build_adapter(venue, symbols):
            async with pg.session() as session:
                await record_market_event(session, event)
            count += 1
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                break
    finally:
        await pg.close()
    return count


async def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", choices=["hyperliquid", "binance"], default="hyperliquid")
    parser.add_argument("--symbols")
    parser.add_argument("--duration", type=int, help="Collection duration in seconds")
    args = parser.parse_args()

    defaults = settings.hyperliquid_symbols if args.venue == "hyperliquid" else settings.crypto_symbols
    symbols = _parse_symbols(args.symbols, defaults)
    count = await collect(venue=args.venue, symbols=symbols, duration=args.duration)
    print(f"recorded {count} {args.venue} events")


if __name__ == "__main__":
    asyncio.run(main())
