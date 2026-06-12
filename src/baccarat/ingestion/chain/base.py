"""Abstract on-chain listener.

The chain listener watches a dynamic set of addresses on Polygon and yields
decoded :class:`OnChainEvent` for any log that touches one of them. It is
deliberately push-based (an async generator) so the strategy layer can react
the moment a block lands rather than polling.

Contract for implementations
----------------------------
* ``add_address`` / ``remove_address`` MUST be safe to call while
  ``stream_events`` is iterating; the implementation re-installs the log
  filter as needed.
* Reorgs: on an L2 the canonical approach is to wait ``N`` confirmations
  before emitting (typically 2-3 on Polygon). Adapters may emit immediately
  for latency-sensitive use cases AND re-emit on confirmation; downstream
  consumers should treat ``OnChainEvent`` as idempotent by ``(tx_hash, log_index)``.
* All RPC calls MUST go through :class:`RpcPool` so failover is transparent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from baccarat.core.types import OnChainEvent


class ChainListener(ABC):
    """Push-based on-chain event listener."""

    @abstractmethod
    async def start(self) -> None:
        """Open RPC subscriptions and start the internal pump task. Idempotent."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel subscriptions and stop the pump task. Idempotent."""

    @abstractmethod
    async def add_address(self, address: str, *, label: str = "") -> None:
        """Begin watching ``address``. Lower-cases internally; safe to call concurrently."""

    @abstractmethod
    async def remove_address(self, address: str) -> None:
        """Stop watching ``address``. No-op if not currently watched."""

    @abstractmethod
    def stream_events(self) -> AsyncIterator[OnChainEvent]:
        """Yield decoded events for any watched address. Iteration is the only consumer interface."""
