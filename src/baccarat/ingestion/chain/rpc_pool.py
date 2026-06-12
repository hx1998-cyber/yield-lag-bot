"""Polygon RPC node pool with health-checked failover.

Every web3 / chain-listener call goes through ``RpcPool.call``. The pool
keeps an ordered list of endpoints and:

* tracks per-endpoint health (latency, error rate, last error time);
* short-circuits to the next endpoint when the current one trips a circuit
  breaker (N consecutive failures within a window);
* periodically health-checks unhealthy endpoints via ``eth_blockNumber`` and
  promotes them back into rotation when they recover.

The business layer never sees an :class:`RpcError` unless every endpoint
in the pool failed for the same logical call.
"""

from __future__ import annotations

from typing import Any

from baccarat.core.config import NetworkSettings
from baccarat.core.exceptions import RpcError
from baccarat.core.logger import get_logger

log = get_logger(__name__)


class RpcPool:
    """Endpoint pool. **M1 stub** — implementation lands in M2."""

    def __init__(self, settings: NetworkSettings):
        self._settings = settings
        self._endpoints: list[str] = list(settings.rpc_endpoints)
        if not self._endpoints:
            raise RpcError("RpcPool requires at least one endpoint")
        self._current_idx: int = 0

    @property
    def current_endpoint(self) -> str:
        return self._endpoints[self._current_idx]

    async def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Issue a JSON-RPC call, transparently failing over on error."""
        raise NotImplementedError("RpcPool.call — implement in M2")

    async def health_check_loop(self) -> None:
        """Background coroutine — probes endpoints, demotes/promotes them."""
        raise NotImplementedError("RpcPool.health_check_loop — implement in M2")
