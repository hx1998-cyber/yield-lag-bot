"""CopyTradeStrategy — mirror smart-money fills.

Algorithm (to be implemented in M3)
-----------------------------------
1. On ``OnChainEvent`` with ``event_name == "OrderFilled"``:
   * Confirm ``event.address`` is in the address pool (it should already be
     filtered upstream, but defense-in-depth).
2. Decode market_id, token_id, side, fill_size_usdc, fill_price.
3. Look up the watched address config (copy_ratio | fixed_size_usdc,
   max_slippage_bps).
4. Compute our size:
   * fixed: ``fixed_size_usdc``
   * proportional: ``copy_ratio * fill_size_usdc``
5. Read current best ask (or bid if exiting) from Redis orderbook mirror.
6. Compute slippage vs. the source's fill price. Reject if it exceeds
   ``max_slippage_bps``.
7. Build a :class:`Signal` with ``time_in_force=GTC``,
   ``expire_at_ms = now_ms + copy_trade.signal_ttl_ms`` and emit it.
"""

from __future__ import annotations

from baccarat.core.config import CopyTradeSettings
from baccarat.core.logger import get_logger
from baccarat.core.types import OnChainEvent, OrderBookSnapshot, Signal
from baccarat.storage.redis_client import RedisClient
from baccarat.strategy.address_pool import AddressPool
from baccarat.strategy.base import Strategy

log = get_logger(__name__)


class CopyTradeStrategy(Strategy):
    name = "copy_trade"

    def __init__(
        self,
        settings: CopyTradeSettings,
        address_pool: AddressPool,
        redis: RedisClient,
    ):
        self._settings = settings
        self._address_pool = address_pool
        self._redis = redis

    async def on_market_data(self, event: OrderBookSnapshot) -> list[Signal]:
        # Copy-trade does not react to market data directly; market state is
        # consulted via the redis mirror inside ``on_chain_event``.
        return []

    async def on_chain_event(self, event: OnChainEvent) -> list[Signal]:
        raise NotImplementedError("CopyTradeStrategy.on_chain_event — implement in M3")

    async def is_halted(self) -> bool:
        raise NotImplementedError("CopyTradeStrategy.is_halted — implement in M3")
