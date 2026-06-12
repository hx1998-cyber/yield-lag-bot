"""Async Redis client wrapper.

Used for:

* Orderbook mirror — ``orderbook:{market_id}:{token_id}`` (HSET / HGETALL).
* Position mirror — ``positions:{market_id}:{token_id}`` (HSET / HGETALL).
* Daily PnL aggregation — ``pnl:daily:{YYYY-MM-DD}`` (HINCRBYFLOAT).
* Strategy halt flags — ``strategy:halted:{strategy_name}`` (SET / GET).
* Signal rate-limit window — ``ratelimit:signals:{minute_bucket}`` (INCR + EXPIRE).

Postgres is truth; Redis is a performance view. After a Redis OOM / restart,
the bot warms the mirrors from Postgres before resuming trading.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from baccarat.core.logger import get_logger

log = get_logger(__name__)


class RedisClient:
    """Thin convenience wrapper around ``redis.asyncio.Redis``."""

    def __init__(self, client: aioredis.Redis):
        self._client = client

    @classmethod
    def from_url(cls, url: str, *, decode_responses: bool = True) -> RedisClient:
        client = aioredis.from_url(
            url,
            decode_responses=decode_responses,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
        )
        return cls(client)

    @property
    def raw(self) -> aioredis.Redis:
        """Escape hatch for advanced commands (pipelines, scripts, pub/sub)."""
        return self._client

    async def healthcheck(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception as exc:
            log.warning("redis.healthcheck.failed", error=str(exc))
            return False

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Convenience helpers — extend as concrete needs surface in M2/M3.
    # Kept thin on purpose: complex workflows belong in domain modules.
    # ------------------------------------------------------------------
    async def hset_mapping(self, key: str, mapping: dict[str, Any]) -> None:
        if not mapping:
            return
        await self._client.hset(key, mapping={k: str(v) for k, v in mapping.items()})

    async def hgetall(self, key: str) -> dict[str, str]:
        result = await self._client.hgetall(key)
        return result if isinstance(result, dict) else {}

    async def set_with_ttl(self, key: str, value: str, ttl_sec: int) -> None:
        await self._client.set(key, value, ex=ttl_sec)
