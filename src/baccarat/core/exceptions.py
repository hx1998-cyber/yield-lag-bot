"""Unified exception hierarchy.

All errors raised by baccarat code MUST inherit from :class:`BaccaratError`.
This lets the orchestrator distinguish controlled failures (which a strategy
should react to) from uncaught bugs (which should crash and restart the
container).

Conventions
-----------
* Pass structured context via ``**kwargs`` instead of f-strings; the structlog
  exception handler will render them as JSON fields.
* Never catch :class:`BaccaratError` blindly — always catch the most specific
  subclass.
* :class:`HedgeFailedError` is reserved for the only situation where automated
  recovery is impossible: the Maker leg of an arbitrage filled but the Taker
  AND the hedge both failed.  Raising it must trigger a strategy-wide halt
  and a Telegram page.
"""

from __future__ import annotations

from typing import Any


class BaccaratError(Exception):
    """Base class for all baccarat-controlled failures."""

    def __init__(self, message: str = "", **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        ctx = " ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{self.message} [{ctx}]"


# ---------------------------------------------------------------------------
# Configuration / startup
# ---------------------------------------------------------------------------
class ConfigError(BaccaratError):
    """Invalid or missing configuration. Always fatal at startup."""


# ---------------------------------------------------------------------------
# Network / RPC
# ---------------------------------------------------------------------------
class RpcError(BaccaratError):
    """Polygon RPC call failed (after the pool exhausted all endpoints)."""


class IngestionError(BaccaratError):
    """Generic ingestion-layer failure (WS dropped, decode failed, …)."""


# ---------------------------------------------------------------------------
# Strategy / risk / execution
# ---------------------------------------------------------------------------
class StrategyError(BaccaratError):
    """Strategy refused to produce a signal due to an internal precondition."""


class RiskRejectError(BaccaratError):
    """Risk manager rejected a signal. ``reason`` should be a stable enum-like string."""

    def __init__(self, reason: str, **context: Any) -> None:
        super().__init__(f"risk rejected: {reason}", reason=reason, **context)
        self.reason = reason


class ExecutionError(BaccaratError):
    """Order placement / on-chain submission failed in a way the executor handled."""


class HedgeFailedError(ExecutionError):
    """Maker leg filled, Taker failed, hedge also failed — naked exposure remains.

    Raising this MUST:
      1. Persist a critical risk_event row.
      2. Set ``strategy_state.is_halted = TRUE`` for the offending strategy.
      3. Page the operator via Telegram.

    The orchestrator does NOT auto-recover from this. Manual unwind required.
    """


class SignalExpiredError(ExecutionError):
    """Signal exceeded its ``expire_at_ms`` before the executor picked it up."""
