"""Gas oracle — dynamic priority fee + USDC-denominated cost estimates.

Uses Polygon's EIP-1559 endpoint (``eth_maxPriorityFeePerGas``) plus a small
percentile model on recent blocks to suggest priority fees. Converts
gas-units → USDC via the current MATIC/USDC price (cached in Redis with
a short TTL).

For arbitrage we need accurate USDC-denominated gas estimates because the
strategy must know "is this still profitable AFTER gas?" before signing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from baccarat.core.logger import get_logger
from baccarat.ingestion.chain.rpc_pool import RpcPool

log = get_logger(__name__)

GasUrgency = Literal["normal", "fast", "urgent"]


class GasOracle:
    """**M1 stub.** Implementation in M4."""

    def __init__(self, rpc_pool: RpcPool):
        self._rpc = rpc_pool

    async def get_priority_fee_wei(self, urgency: GasUrgency = "normal") -> int:
        raise NotImplementedError("GasOracle.get_priority_fee_wei — implement in M4")

    async def estimate_tx_cost_usdc(self, gas_units: int, urgency: GasUrgency = "normal") -> Decimal:
        """Returns the projected gas cost in USDC. Used by ArbitrageStrategy."""
        raise NotImplementedError("GasOracle.estimate_tx_cost_usdc — implement in M4")
