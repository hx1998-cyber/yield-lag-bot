"""M1 application entrypoint."""

from __future__ import annotations

import asyncio
import sys
from typing import NoReturn

from baccarat.core.logger import setup_logging
from baccarat.storage.postgres import PostgresClient
from baccarat.storage.redis_client import RedisClient

from yield_lag_bot.config import load_settings


async def main() -> int:
    settings = load_settings()
    setup_logging(level=settings.log_level, fmt="console", include_trace_id=False)

    pg = PostgresClient.from_url(
        settings.database_url,
        pool_min_size=settings.postgres_pool_min_size,
        pool_max_size=settings.postgres_pool_max_size,
    )
    redis = RedisClient.from_url(settings.redis_url)
    try:
        pg_ok = await pg.healthcheck()
        redis_ok = await redis.healthcheck()
        if not pg_ok or not redis_ok:
            return 2
        print(
            "Project YIELD-LAG M1 ready: public data/research mode, "
            f"LIVE_TRADING={settings.live_trading}, PAPER_TRADING={settings.paper_trading}",
            flush=True,
        )
        return 0
    finally:
        await pg.close()
        await redis.close()


def run() -> NoReturn:
    try:
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    run()
