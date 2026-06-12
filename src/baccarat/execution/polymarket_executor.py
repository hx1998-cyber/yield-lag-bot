"""Polymarket executor — drives the Maker → Taker → Merge state machine.

This is THE riskiest module in the system. Every code path here either
locks in profit or eats a loss, and the lifetime of a signal is measured
in milliseconds. Treat the docstring sequence below as a contract.

Signal lifecycle (M3 / M4)
--------------------------

CopyTrade signal (single leg):
    submit(signal)
      → drop if expired
      → POST /order to CLOB (signed via Wallet.sign_eip712)
      → poll order status until terminal (FILLED / PARTIAL / CANCELLED / EXPIRED)
      → write trades row + apply_fill on PositionManager
      → return ExecutionResult

Arbitrage MAKER signal:
    submit(signal)  with leg_role=MAKER, time_in_force=GTC, expire_at_ms set
      → drop if expired
      → POST /order (limit, post-only) to CLOB
      → write trades row(status=PENDING)
      → return immediately — the orchestrator will dispatch the TAKER signal
        when it observes the Maker fill via the user channel.

Arbitrage TAKER signal:
    submit(signal)  with leg_role=TAKER, time_in_force=FOK, parent_signal_id set
      → drop if expired
      → look up parent maker trade row; ABORT if maker not yet FILLED
      → POST /order (FOK) to CLOB
      → on FILLED: build merge tx via TxBuilder.build_merge → submit → watch
        → on confirm: realized_pnl = 1 - cost - fee - gas
      → on FAIL or PARTIAL: trigger HEDGE flow:
          * Build a market-IOC sell on the maker leg via build_hedge()
          * If hedge fills → status HEDGED, log loss, return
          * If hedge fails → raise HedgeFailedError → orchestrator halts strategy

Cancellation
------------
``cancel(clob_order_id)`` — used by the orchestrator when a Maker signal's
``expire_at_ms`` elapses without a fill.
"""

from __future__ import annotations

from baccarat.core.config import PolymarketSettings
from baccarat.core.logger import get_logger
from baccarat.core.types import ExecutionResult, Signal
from baccarat.execution.base import Executor
from baccarat.execution.gas_oracle import GasOracle
from baccarat.execution.position_manager import PositionManager
from baccarat.execution.tx_builder import TxBuilder
from baccarat.execution.tx_submitter import TxSubmitter
from baccarat.execution.wallet import Wallet
from baccarat.storage.postgres import PostgresClient

log = get_logger(__name__)


class PolymarketExecutor(Executor):
    """**M1 stub.** Implementation lands in M3 (CLOB legs) + M4 (on-chain merge)."""

    def __init__(
        self,
        settings: PolymarketSettings,
        wallet: Wallet,
        gas: GasOracle,
        tx_builder: TxBuilder,
        tx_submitter: TxSubmitter,
        positions: PositionManager,
        db: PostgresClient,
    ):
        self._settings = settings
        self._wallet = wallet
        self._gas = gas
        self._tx_builder = tx_builder
        self._tx_submitter = tx_submitter
        self._positions = positions
        self._db = db

    async def submit(self, signal: Signal) -> ExecutionResult:
        raise NotImplementedError("PolymarketExecutor.submit — implement in M3/M4")

    async def cancel(self, clob_order_id: str) -> bool:
        raise NotImplementedError("PolymarketExecutor.cancel — implement in M3")
