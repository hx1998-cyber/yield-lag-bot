"""Export normalized ticks from Postgres to CSV."""

from __future__ import annotations

import argparse
import asyncio

from baccarat.storage.postgres import PostgresClient

from yield_lag_bot.config import load_settings
from yield_lag_bot.data.recorder import export_market_ticks_csv


def _parse_symbols(value: str) -> list[str]:
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", default="hyperliquid")
    parser.add_argument("--symbols", default="BTC,ETH")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    settings = load_settings()
    pg = PostgresClient.from_url(
        settings.database_url,
        pool_min_size=settings.postgres_pool_min_size,
        pool_max_size=settings.postgres_pool_max_size,
    )
    try:
        async with pg.session() as session:
            await export_market_ticks_csv(
                session,
                venue=args.venue,
                symbols=_parse_symbols(args.symbols),
                out=args.out,
            )
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
