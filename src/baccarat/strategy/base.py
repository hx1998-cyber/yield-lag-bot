"""Strategy base class.

A strategy reacts to upstream events (orderbook updates, on-chain logs) and
emits zero or more :class:`Signal` objects. Strategies MUST be:

* **Stateless or DB-backed.** Anything kept only in memory is lost on
  restart. Use Redis (hot) + Postgres (truth) for any persistent state.
* **Idempotent.** The same upstream event may arrive twice (reorgs,
  reconnects). De-duplicate by ``(tx_hash, log_index)`` for chain events
  and by ``ts_ms`` + content for market events.
* **Fast.** ``on_*`` handlers run on the same event loop as ingestion;
  blocking work goes to a Redis-backed queue or a separate task.
* **Cancel-safe.** Strategies may be halted via the strategy_state table
  at any moment; check ``self.is_halted()`` before emitting.

Implementations live in :mod:`baccarat.strategy.copy_trade` and
:mod:`baccarat.strategy.arbitrage`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from baccarat.core.types import OnChainEvent, OrderBookSnapshot, Signal


class Strategy(ABC):
    """Abstract trading strategy."""

    name: str

    @abstractmethod
    async def on_market_data(self, event: OrderBookSnapshot) -> list[Signal]:
        """React to an orderbook snapshot. Return any signals to emit."""

    @abstractmethod
    async def on_chain_event(self, event: OnChainEvent) -> list[Signal]:
        """React to an on-chain event. Return any signals to emit."""

    @abstractmethod
    async def is_halted(self) -> bool:
        """Return True if the strategy_state row says this strategy is halted."""
