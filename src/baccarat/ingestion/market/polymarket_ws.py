"""Polymarket CLOB WebSocket adapter.

Connects to ``wss://ws-subscriptions-clob.polymarket.com``, subscribes to
the ``market`` channel for one or more outcome tokens, and translates the
incremental ``book`` / ``price_change`` / ``last_trade_price`` messages into
:class:`OrderBookSnapshot` / :class:`Trade` events.

Implementation notes (deferred to M2)
-------------------------------------
* Polymarket sends a ``book`` message with full depth on subscribe and
  ``price_change`` deltas afterwards. Maintain a sorted dict per token
  and emit a snapshot whenever a message materially changes the top-of-book.
* The bot must also subscribe to its own user channel (signed) for order
  fills — but that lives in the executor, not here.
* Reconnection: exponential backoff capped at
  ``settings.polymarket.reconnect_max_delay_sec``. On reconnect, resubscribe
  every active token and emit a fresh snapshot before any deltas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from baccarat.core.config import PolymarketSettings
from baccarat.core.logger import get_logger
from baccarat.core.types import MarketInfo, OrderBookSnapshot, Trade
from baccarat.ingestion.market.base import MarketDataSource
from baccarat.storage.redis_client import RedisClient

log = get_logger(__name__)


class PolymarketWsSource(MarketDataSource):
    """Polymarket CLOB WS adapter. **M1 stub** — no I/O yet."""

    def __init__(self, settings: PolymarketSettings, redis: RedisClient):
        self._settings = settings
        self._redis = redis

    async def connect(self) -> None:
        raise NotImplementedError("Polymarket WS connect — implement in M2")

    async def disconnect(self) -> None:
        raise NotImplementedError("Polymarket WS disconnect — implement in M2")

    def subscribe_orderbook(self, market_id: str) -> AsyncIterator[OrderBookSnapshot]:
        raise NotImplementedError("Polymarket WS orderbook subscription — implement in M2")

    def subscribe_trades(self, market_id: str) -> AsyncIterator[Trade]:
        raise NotImplementedError("Polymarket WS trades subscription — implement in M2")

    async def get_market_info(self, market_id: str) -> MarketInfo:
        raise NotImplementedError("Polymarket REST market info — implement in M2")
