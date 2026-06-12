"""Abstract executor.

The executor is the only part of the system that signs anything. Everything
upstream (strategy, risk) produces :class:`Signal` objects, the executor
turns them into either CLOB orders (signed via EIP-712) or on-chain
transactions (signed via the wallet).

Contract for implementations
----------------------------
* ``submit`` MUST drop expired signals before doing any I/O. Use
  ``Signal.is_expired()`` as the first line.
* ``submit`` MUST be safe to call concurrently for different signals
  (multiple maker arbs, copy-trades, …); internally it serializes
  whatever needs serializing (e.g. nonce assignment).
* On any failure, the executor MUST persist a corresponding ``trades``
  row with the appropriate ``TradeStatus``, then return an
  :class:`ExecutionResult` describing the outcome — never raise to the
  caller for *expected* failures (slippage, gas, partial fills).
* :class:`HedgeFailedError` is the one exception: that's the unrecoverable
  case and must propagate so the orchestrator can halt the strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from baccarat.core.types import ExecutionResult, Signal


class Executor(ABC):
    @abstractmethod
    async def submit(self, signal: Signal) -> ExecutionResult:
        """Place / send / settle the signal. Persists trade rows. Drops if expired."""

    @abstractmethod
    async def cancel(self, clob_order_id: str) -> bool:
        """Cancel a resting CLOB order. Returns True if the cancel was accepted."""
