"""Position manager.

Owns writes to the ``positions`` table AND its Redis mirror. Single writer
guarantees the two stay consistent without distributed locks.

Update flow
-----------
On every fill (PARTIAL or FILLED ``trades`` row):
1. Open a Postgres transaction.
2. Read current ``positions`` row for ``(market_id, token_id)`` (FOR UPDATE).
3. Recompute ``current_size``, ``average_entry_price``, ``cost_basis_usdc``.
4. Write back. Commit.
5. After commit, write the updated snapshot to
   ``positions:{market_id}:{token_id}`` in Redis (HSET).

Reads
-----
The risk manager reads ONLY from Redis for hot-path checks. On Redis OOM /
restart, :meth:`warmup_redis` rebuilds the mirror from Postgres before
trading resumes.
"""

from __future__ import annotations

from baccarat.core.logger import get_logger
from baccarat.core.types import ExecutionResult
from baccarat.storage.postgres import PostgresClient
from baccarat.storage.redis_client import RedisClient

log = get_logger(__name__)


class PositionManager:
    """**M1 stub.**"""

    def __init__(self, db: PostgresClient, redis: RedisClient):
        self._db = db
        self._redis = redis

    async def warmup_redis(self) -> None:
        """Rebuild the Redis position mirror from Postgres. Call on startup."""
        raise NotImplementedError("PositionManager.warmup_redis — implement in M3")

    async def apply_fill(self, signal_id: int, result: ExecutionResult) -> None:
        """Update the position table + Redis mirror after a fill.

        Must be called from the executor right after the trades row is updated,
        within the same async task to preserve ordering.
        """
        raise NotImplementedError("PositionManager.apply_fill — implement in M3")
