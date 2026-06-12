"""ArbitrageStrategy — Yes + No < 1 USDC merge-redeem.

Detection (this module, M3)
---------------------------
On every orderbook snapshot for either outcome of a market:

1. Read the *other* outcome's best ask from the Redis mirror (so we don't
   need to wait for both legs to update).
2. Compute ``total_cost = yes_ask + no_ask``.
3. ``estimated_fee = est_taker_fee(total_cost)`` — placeholder while
   Polymarket charges 0% but kept because rules can change overnight.
4. ``estimated_gas = gas_oracle.estimate_merge_redeem_cost_usdc()``.
5. ``profit = 1 - total_cost - estimated_fee - estimated_gas``.
6. Apply ``safety_margin_bps`` and the global ``risk.min_arb_profit_*`` floors.
7. If profit clears the bar:
   * Pick the *thin* leg (smaller depth above mid) → MAKER limit.
   * Build the MAKER signal with ``time_in_force=GTC``,
     ``expire_at_ms = now + arbitrage.maker_timeout_ms``.
   * Build the TAKER signal with ``time_in_force=FOK``,
     ``parent_signal_id`` referencing the maker (assigned after maker DB insert).
   * Build the HEDGE template (not yet emitted) — the executor's state
     machine fills it in if the taker fails.
8. Persist an ``arbitrage_opportunities`` row whether or not we executed,
   so we can analyze hit rate later.

Execution (lives in :mod:`baccarat.execution.polymarket_executor`)
------------------------------------------------------------------
The strategy NEVER submits both legs in parallel. The executor's state
machine drives the Maker → Taker → Merge flow; if Taker fails it tries the
HEDGE; if HEDGE also fails it raises :class:`HedgeFailedError` and halts
the whole strategy.
"""

from __future__ import annotations

from baccarat.core.config import ArbitrageSettings
from baccarat.core.logger import get_logger
from baccarat.core.types import OnChainEvent, OrderBookSnapshot, Signal
from baccarat.storage.redis_client import RedisClient
from baccarat.strategy.base import Strategy

log = get_logger(__name__)


class ArbitrageStrategy(Strategy):
    name = "arbitrage"

    def __init__(self, settings: ArbitrageSettings, redis: RedisClient):
        self._settings = settings
        self._redis = redis

    async def on_market_data(self, event: OrderBookSnapshot) -> list[Signal]:
        raise NotImplementedError("ArbitrageStrategy.on_market_data — implement in M3")

    async def on_chain_event(self, event: OnChainEvent) -> list[Signal]:
        # Arbitrage doesn't react to chain events; merge/redeem is initiated
        # by the executor after both legs settle.
        return []

    async def is_halted(self) -> bool:
        raise NotImplementedError("ArbitrageStrategy.is_halted — implement in M3")
