"""Reject reasons (stable enum-like strings).

These strings end up in:
* ``signals.reject_reason``
* ``risk_events.event_type``
* Telegram alerts
* Logs

Treat them as a public API — renaming a value is a schema change.
"""

from __future__ import annotations

from enum import Enum


class RejectReason(str, Enum):
    SIZE_EXCEEDED = "SIZE_EXCEEDED"                  # size_usdc > max_position_size_usdc
    OPEN_POSITIONS_EXCEEDED = "OPEN_POSITIONS_EXCEEDED"
    DAILY_DRAWDOWN_HIT = "DAILY_DRAWDOWN_HIT"        # circuit breaker tripped
    SIGNAL_RATE_EXCEEDED = "SIGNAL_RATE_EXCEEDED"    # too many signals/min
    ARB_PROFIT_TOO_LOW = "ARB_PROFIT_TOO_LOW"        # below abs floor or bps floor
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"                # signal arrived past expire_at_ms
    STRATEGY_HALTED = "STRATEGY_HALTED"              # strategy_state.is_halted=true
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"    # checked just-in-time before execute
    INVARIANT_VIOLATED = "INVARIANT_VIOLATED"        # catch-all for defensive checks
