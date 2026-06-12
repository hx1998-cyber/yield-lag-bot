"""Smart-money address pool.

Source of truth: ``smart_money_addresses`` table.
Hot lookup cache: Redis hash ``smart_money:by_address`` for sub-millisecond
``contains`` / per-address-config lookups inside the copy-trade hot path.

The pool exposes a small dataclass-friendly view; adding/removing addresses
goes through the ORM so audit timestamps stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from baccarat.core.logger import get_logger
from baccarat.storage.postgres import PostgresClient
from baccarat.storage.redis_client import RedisClient

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WatchedAddress:
    address: str  # lowercased
    label: str
    copy_ratio: Decimal | None
    fixed_size_usdc: Decimal | None
    max_slippage_bps: int


class AddressPool:
    """Backed by Postgres, fronted by Redis. **M1 stub.**"""

    def __init__(self, db: PostgresClient, redis: RedisClient):
        self._db = db
        self._redis = redis

    async def warmup(self) -> None:
        """Load the full enabled set into Redis on boot. Implement in M2."""
        raise NotImplementedError("AddressPool.warmup — implement in M2")

    async def add(self, address: WatchedAddress) -> None:
        raise NotImplementedError("AddressPool.add — implement in M2")

    async def remove(self, address: str) -> None:
        raise NotImplementedError("AddressPool.remove — implement in M2")

    async def get(self, address: str) -> WatchedAddress | None:
        """Hot-path lookup. Reads Redis only; never blocks on Postgres."""
        raise NotImplementedError("AddressPool.get — implement in M2")
