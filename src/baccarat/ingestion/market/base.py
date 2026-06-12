"""Abstract market-data source.

Implementations adapt a specific exchange to baccarat's normalized event
types. The strategy layer only sees :class:`OrderBookSnapshot` and
:class:`Trade` — it never knows whether the source is Polymarket, Kalshi,
or anything else.

Contract for implementations
----------------------------
* ``connect()`` MUST be idempotent and safe to call after a previous
  ``disconnect()``.
* All ``subscribe_*`` methods are async generators that ``yield`` on each
  update. They MUST handle their own reconnection internally (with
  exponential backoff capped by config) and MUST resubscribe transparently
  after a reconnect — the consumer never sees a gap.
* If the underlying transport delivers incremental updates, the adapter
  must coalesce them into full snapshots before yielding. Strategies treat
  every yield as authoritative.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from baccarat.core.types import MarketInfo, OrderBookSnapshot, Trade


class MarketDataSource(ABC):
    """Cross-platform market data interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the underlying transport (WS / REST session). Idempotent."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the transport. Idempotent."""

    @abstractmethod
    def subscribe_orderbook(self, market_id: str) -> AsyncIterator[OrderBookSnapshot]:
        """Yield full orderbook snapshots for ``market_id`` until cancelled.

        The generator is responsible for:
          * subscribing on first iteration,
          * coalescing incremental updates into full snapshots,
          * reconnecting + resubscribing on any transport error.
        """

    @abstractmethod
    def subscribe_trades(self, market_id: str) -> AsyncIterator[Trade]:
        """Yield trade prints for ``market_id`` until cancelled."""

    @abstractmethod
    async def get_market_info(self, market_id: str) -> MarketInfo:
        """Fetch (and cache) static metadata for a market."""
