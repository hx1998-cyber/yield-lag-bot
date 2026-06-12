"""Concrete :class:`ChainListener` for Polygon.

Subscribes to ``eth_logs`` matching Polymarket Exchange + ConditionalTokens
addresses, filters by watched address set, decodes via :class:`EventDecoder`,
and yields :class:`OnChainEvent`. **M1 stub.**
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from baccarat.core.logger import get_logger
from baccarat.core.types import OnChainEvent
from baccarat.ingestion.chain.base import ChainListener
from baccarat.ingestion.chain.event_decoder import EventDecoder
from baccarat.ingestion.chain.rpc_pool import RpcPool

log = get_logger(__name__)


class PolygonListener(ChainListener):
    """Polygon-specific listener built on :class:`RpcPool`."""

    def __init__(
        self,
        rpc_pool: RpcPool,
        decoder: EventDecoder,
        *,
        polymarket_contract_addresses: list[str],
    ):
        self._rpc = rpc_pool
        self._decoder = decoder
        self._contracts = [a.lower() for a in polymarket_contract_addresses]
        self._watched: set[str] = set()

    async def start(self) -> None:
        raise NotImplementedError("PolygonListener.start — implement in M2")

    async def stop(self) -> None:
        raise NotImplementedError("PolygonListener.stop — implement in M2")

    async def add_address(self, address: str, *, label: str = "") -> None:
        raise NotImplementedError("PolygonListener.add_address — implement in M2")

    async def remove_address(self, address: str) -> None:
        raise NotImplementedError("PolygonListener.remove_address — implement in M2")

    def stream_events(self) -> AsyncIterator[OnChainEvent]:
        raise NotImplementedError("PolygonListener.stream_events — implement in M2")
