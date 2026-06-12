"""Risk manager — the only gate between strategy and executor.

A signal does not reach the executor unless ``RiskManager.check`` returns
``RiskDecision.APPROVE``. The checks are intentionally cheap (Redis-only
hot reads) so this never becomes a bottleneck.

Hard checks (in order, fail-fast):

1. :data:`RejectReason.SIGNAL_EXPIRED` — ``signal.is_expired()``.
2. :data:`RejectReason.STRATEGY_HALTED` — Redis flag ``strategy:halted:{name}``.
3. :data:`RejectReason.SIZE_EXCEEDED` — ``size_usdc > max_position_size_usdc``.
4. :data:`RejectReason.DAILY_DRAWDOWN_HIT` — Redis ``pnl:daily:today.realized``
   below ``-max_daily_drawdown_usdc``. Once tripped, all subsequent signals
   are rejected until the next UTC day rolls over OR the operator clears
   the flag.
5. :data:`RejectReason.OPEN_POSITIONS_EXCEEDED` — count of ``positions``
   rows from the Redis mirror.
6. :data:`RejectReason.SIGNAL_RATE_EXCEEDED` — sliding window counter in Redis.
7. :data:`RejectReason.ARB_PROFIT_TOO_LOW` — only for ``ARBITRAGE`` source;
   ``expected_profit_usdc`` below the abs/bps floor.
8. :data:`RejectReason.INVARIANT_VIOLATED` — defensive: missing fields, NaN, …

Side effects of a rejection:
* Persist a ``risk_events`` row.
* Update the signal's ``status``/``reject_reason``.
* If the trip is the daily drawdown, ALSO halt the source strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from baccarat.core.config import RiskSettings
from baccarat.core.logger import get_logger
from baccarat.core.types import Signal
from baccarat.risk.limits import RejectReason
from baccarat.storage.postgres import PostgresClient
from baccarat.storage.redis_client import RedisClient

log = get_logger(__name__)


class RiskDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class RiskOutcome:
    decision: RiskDecision
    reason: RejectReason | None = None
    detail: str | None = None


class RiskManager:
    """**M1 stub.** Implementation in M3."""

    def __init__(
        self,
        settings: RiskSettings,
        redis: RedisClient,
        db: PostgresClient,
    ):
        self._settings = settings
        self._redis = redis
        self._db = db

    async def check(self, signal: Signal) -> RiskOutcome:
        """Run all hard checks. Returns APPROVE or REJECT(reason)."""
        raise NotImplementedError("RiskManager.check — implement in M3")

    async def on_trade_settled(
        self, signal_id: int, realized_pnl_usdc: float
    ) -> None:
        """Update daily PnL aggregates. Trips the breaker if drawdown breached."""
        raise NotImplementedError("RiskManager.on_trade_settled — implement in M3")

    async def halt_strategy(
        self, strategy_name: str, reason: str, *, halted_by: str = "AUTO"
    ) -> None:
        """Persist halt + Redis flag. Strategies check the flag before emitting."""
        raise NotImplementedError("RiskManager.halt_strategy — implement in M3")
