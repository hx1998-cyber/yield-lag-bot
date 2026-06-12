"""Common dataclasses and enums used across all modules.

Design rules
------------
* All money / price / size fields are :class:`decimal.Decimal`. Do **not**
  introduce ``float`` here — it leaks into the rest of the pipeline and
  corrupts rounding.
* All timestamps in transit are ``int`` epoch milliseconds (UTC). Only
  storage models use ``datetime``.
* Dataclasses are ``frozen=True`` whenever they represent immutable events
  (orderbook snapshot, on-chain log, …). Strategy-mutable structures
  (Signal, Position) are plain dataclasses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class Side(str, Enum):
    """Polymarket has two outcomes per binary market: YES and NO."""

    YES = "YES"
    NO = "NO"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class TimeInForce(str, Enum):
    """CLOB order lifetimes.

    * ``GTC`` — sit on the book until cancelled. Used by Maker arb leg + copy-trade LIMIT.
    * ``IOC`` — fill what you can immediately, cancel the rest.
    * ``FOK`` — fill the entire size or cancel. **Required** for Taker arb leg.
    * ``GTD`` — like GTC, but auto-cancels at ``expire_at_ms``.
    """

    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTD = "GTD"


class SignalSource(str, Enum):
    COPY_TRADE = "COPY_TRADE"
    ARBITRAGE = "ARBITRAGE"


class SignalStatus(str, Enum):
    """Lifecycle states for a signal in the ``signals`` table."""

    PENDING = "PENDING"           # Created, not yet risk-checked
    REJECTED = "REJECTED"         # Risk manager said no
    EXPIRED = "EXPIRED"           # TTL elapsed before execution
    SUBMITTED = "SUBMITTED"       # Sent to CLOB / mempool
    CONFIRMED = "CONFIRMED"       # Settled successfully
    FAILED = "FAILED"             # Submission or settlement failed
    ABORTED_GAS = "ABORTED_GAS"   # Profit eaten by gas, executor declined
    HEDGED = "HEDGED"             # Maker filled, Taker failed, hedge succeeded
    HALTED = "HALTED"             # Hedge also failed; manual intervention needed


class TradeStatus(str, Enum):
    """Lifecycle states for a single ``trades`` row (one row per leg)."""

    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"  # Speed-up / cancel-replace on Polygon


class LegRole(str, Enum):
    """Which role a trade plays inside a multi-leg signal."""

    SOLO = "SOLO"      # CopyTrade: just one leg
    MAKER = "MAKER"    # Arb: thin side, posted first
    TAKER = "TAKER"    # Arb: thick side, FOK after maker fills
    HEDGE = "HEDGE"    # Arb fallback: market-sell maker leg if taker failed


# ---------------------------------------------------------------------------
# Market data (immutable events)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """Single price level. ``price`` is in [0, 1]; ``size`` is USDC notional."""

    price: Decimal
    size: Decimal


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Complete orderbook at a single instant.

    Adapters that receive incremental WS updates MUST coalesce them into full
    snapshots before yielding, so downstream consumers can treat every event
    as authoritative.
    """

    market_id: str           # Polymarket condition_id (0x...32 bytes)
    token_id: str            # Outcome token id (uint256, base-10 string)
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    ts_ms: int               # Source timestamp; falls back to local time if missing

    @property
    def best_bid(self) -> OrderBookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> OrderBookLevel | None:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True, slots=True)
class Trade:
    """A single trade print on a Polymarket outcome token."""

    market_id: str
    token_id: str
    price: Decimal
    size: Decimal
    side_taken: Side
    ts_ms: int


@dataclass(frozen=True, slots=True)
class MarketInfo:
    """Static metadata for a Polymarket market (cached aggressively)."""

    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    end_date: datetime | None
    is_active: bool


# ---------------------------------------------------------------------------
# On-chain events
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OnChainEvent:
    """A decoded log involving a watched address.

    The chain listener filters events to those that touch a watched address;
    decoding into ``decoded`` is event-specific (OrderFilled, PositionSplit,
    PositionMerge, PositionRedeem, …). Strategies should treat ``event_name``
    as the discriminator.
    """

    address: str             # Watched smart-money address (lowercased, checksum elsewhere)
    tx_hash: str
    block_number: int
    log_index: int
    event_name: str
    decoded: dict[str, Any]
    ts_ms: int


# ---------------------------------------------------------------------------
# Signal — strategy → risk → executor
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Signal:
    """A trading intent.

    Created by a strategy, vetted by the risk manager, consumed by the executor.
    Mutable on purpose — risk and executor stamp ``status``/``id`` on it as
    they go.
    """

    source: SignalSource
    strategy_name: str
    market_id: str
    token_id: str
    side: Side
    order_type: OrderType
    size_usdc: Decimal
    limit_price: Decimal
    max_slippage_bps: int
    expected_profit_usdc: Decimal
    metadata: dict[str, Any] = field(default_factory=dict)

    # Lifecycle
    id: int | None = None                       # Postgres bigserial; None until persisted
    status: SignalStatus = SignalStatus.PENDING
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    # Time-in-Force
    time_in_force: TimeInForce = TimeInForce.GTC
    expire_at_ms: int = 0                       # 0 = no expiry

    # Multi-leg coordination (arbitrage)
    leg_role: LegRole = LegRole.SOLO
    parent_signal_id: int | None = None         # Taker / Hedge points back to its Maker

    @property
    def trace_id(self) -> str:
        """Stable id used in logs. Falls back to a temp id until DB assignment."""
        return f"sig-{self.id}" if self.id is not None else f"tmp-{id(self):x}"

    def is_expired(self, now_ms: int | None = None) -> bool:
        if self.expire_at_ms == 0:
            return False
        return (now_ms if now_ms is not None else int(time.time() * 1000)) >= self.expire_at_ms


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ExecutionResult:
    """Returned by ``Executor.submit``.

    Every field is optional except ``status`` — the executor fills in whatever
    it learned during submission.
    """

    status: TradeStatus
    signal_id: int | None = None
    clob_order_id: str | None = None
    tx_hash: str | None = None
    filled_size_usdc: Decimal = Decimal(0)
    average_price: Decimal | None = None
    fee_paid_usdc: Decimal = Decimal(0)
    gas_cost_usdc: Decimal = Decimal(0)
    realized_pnl_usdc: Decimal | None = None
    reason: str | None = None      # Populated when status is FAILED / EXPIRED / CANCELLED


# ---------------------------------------------------------------------------
# Position — current open exposure
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Position:
    """Aggregate exposure on (market_id, token_id).

    Source of truth: ``positions`` table. Redis keeps a mirror keyed by
    ``positions:{market_id}:{token_id}`` for risk-manager hot reads.
    """

    market_id: str
    token_id: str
    side: Side
    current_size: Decimal
    average_entry_price: Decimal
    cost_basis_usdc: Decimal
    unrealized_pnl_usdc: Decimal = Decimal(0)
    last_mark_price: Decimal | None = None
    last_mark_at_ms: int | None = None
