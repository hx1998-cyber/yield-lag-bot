"""Transaction submitter — broadcast, watch, retry, replace, cancel.

Submission flow (M4)
--------------------
1. Broadcast signed tx via :meth:`RpcPool.call("eth_sendRawTransaction", ...)`.
2. Spawn a watcher task that waits for the receipt with a 30s timeout.
3. On timeout:
   * If still pending in mempool, try a speed-up: build the same tx with the
     same nonce but ``maxPriorityFeePerGas * 1.25``, sign, broadcast.
   * If we want to abandon (e.g. price moved, signal expired), broadcast a
     0-value self-transfer with the same nonce to evict ours.
4. On revert, classify by error reason; re-attempt only for transient
   classes (under-priced, replacement under-priced). Never retry on slippage,
   nonce-too-low, or insufficient-funds.
5. After ``alerting.alert_on_consecutive_failures`` consecutive failures,
   page the operator.
"""

from __future__ import annotations

from typing import Any

from baccarat.core.logger import get_logger
from baccarat.ingestion.chain.rpc_pool import RpcPool

log = get_logger(__name__)


class TxSubmitter:
    """**M1 stub.**"""

    def __init__(self, rpc_pool: RpcPool):
        self._rpc = rpc_pool

    async def submit(self, signed_tx_hex: str) -> str:
        """Broadcast. Returns tx_hash. Does NOT wait for receipt."""
        raise NotImplementedError("TxSubmitter.submit — implement in M4")

    async def watch_receipt(self, tx_hash: str, timeout_sec: float = 30.0) -> dict[str, Any] | None:
        """Wait for the receipt or timeout. ``None`` on timeout."""
        raise NotImplementedError("TxSubmitter.watch_receipt — implement in M4")

    async def speed_up(
        self,
        original_tx: dict[str, Any],
        *,
        nonce: int,
        new_priority_fee_wei: int,
    ) -> str:
        raise NotImplementedError("TxSubmitter.speed_up — implement in M4")

    async def cancel(self, nonce: int, *, from_address: str) -> str:
        """Broadcast a 0-value self-transfer to evict the in-flight tx at ``nonce``."""
        raise NotImplementedError("TxSubmitter.cancel — implement in M4")
