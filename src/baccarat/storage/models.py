"""SQLAlchemy 2.0 ORM models — single source of truth for the schema.

Conventions
-----------
* All money / price columns are ``NUMERIC`` (Postgres exact decimal).
* All timestamps are ``TIMESTAMPTZ``; the application is UTC end-to-end.
* Enum-like columns are stored as ``VARCHAR`` to keep migrations cheap; the
  enum type lives in :mod:`baccarat.core.types` and is enforced at the app
  layer. Add a CHECK constraint here if you want belt + braces.
* Indexes target the actual hot read paths (status filters, FK joins). Add
  more sparingly — every index slows writes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base. All models inherit from here so Alembic autogen sees them."""


# ---------------------------------------------------------------------------
# markets — static metadata, refreshed lazily.
# ---------------------------------------------------------------------------
class Market(Base):
    __tablename__ = "markets"

    condition_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    yes_token_id: Mapped[str] = mapped_column(String(78), nullable=False)
    no_token_id: Mapped[str] = mapped_column(String(78), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_markets_status", "status"),
    )


# ---------------------------------------------------------------------------
# smart_money_addresses — copy-trade source addresses.
# ---------------------------------------------------------------------------
class SmartMoneyAddress(Base):
    __tablename__ = "smart_money_addresses"

    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(100))
    # Either copy_ratio (proportional) OR fixed_size_usdc (absolute) — not both.
    copy_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    fixed_size_usdc: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    max_slippage_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(copy_ratio IS NOT NULL) OR (fixed_size_usdc IS NOT NULL)",
            name="ck_smart_money_size_specified",
        ),
        Index("idx_smart_money_enabled", "enabled"),
    )


# ---------------------------------------------------------------------------
# signals — every intent, including rejected & expired ones (for audit).
# ---------------------------------------------------------------------------
class SignalRow(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False)
    market_id: Mapped[str] = mapped_column(String(66), nullable=False)
    token_id: Mapped[str] = mapped_column(String(78), nullable=False)
    side: Mapped[str | None] = mapped_column(String(3))
    order_type: Mapped[str | None] = mapped_column(String(10))
    size_usdc: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    expected_profit_usdc: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    time_in_force: Mapped[str] = mapped_column(String(5), nullable=False, default="GTC")
    expire_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    leg_role: Mapped[str] = mapped_column(String(10), nullable=False, default="SOLO")
    parent_signal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("signals.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    reject_reason: Mapped[str | None] = mapped_column(Text)
    signal_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trades: Mapped[list[TradeRow]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_signals_status_created", "status", "created_at"),
        Index("idx_signals_market", "market_id"),
        Index("idx_signals_parent", "parent_signal_id"),
    )


# ---------------------------------------------------------------------------
# trades — one row per leg per CLOB order or on-chain tx.
# ---------------------------------------------------------------------------
class TradeRow(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    leg_role: Mapped[str] = mapped_column(String(10), nullable=False, default="SOLO")

    # CLOB identifier (off-chain orders).
    clob_order_id: Mapped[str | None] = mapped_column(String(100), unique=True)

    # On-chain identifier (Approve / Merge / Redeem).
    tx_hash: Mapped[str | None] = mapped_column(String(66), unique=True)
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    block_number: Mapped[int | None] = mapped_column(BigInteger)

    # Order vs. actual fill.
    requested_size_usdc: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    filled_size_usdc: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal(0)
    )
    requested_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    # Fees & gas.
    fee_paid_usdc: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal(0)
    )
    gas_used: Mapped[int | None] = mapped_column(BigInteger)
    gas_price_wei: Mapped[Decimal | None] = mapped_column(Numeric(30, 0))
    gas_cost_usdc: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))

    realized_pnl_usdc: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    signal: Mapped[SignalRow] = relationship(back_populates="trades")

    __table_args__ = (
        CheckConstraint(
            "filled_size_usdc <= requested_size_usdc",
            name="ck_trades_fill_le_request",
        ),
        Index("idx_trades_status_submitted", "status", "submitted_at"),
        Index("idx_trades_signal", "signal_id"),
    )


# ---------------------------------------------------------------------------
# positions — current open exposure. Risk reads from a Redis mirror; this is truth.
# ---------------------------------------------------------------------------
class PositionRow(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(66), nullable=False)
    token_id: Mapped[str] = mapped_column(String(78), nullable=False)
    side: Mapped[str] = mapped_column(String(3), nullable=False)

    current_size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    cost_basis_usdc: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    unrealized_pnl_usdc: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal(0)
    )
    last_mark_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    last_mark_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("market_id", "token_id", name="uq_positions_market_token"),
        Index("idx_positions_market", "market_id"),
    )


# ---------------------------------------------------------------------------
# arbitrage_opportunities — every detected opportunity, executed or not.
# Lets us measure hit rate / competition / latency post-hoc.
# ---------------------------------------------------------------------------
class ArbitrageOpportunity(Base):
    __tablename__ = "arbitrage_opportunities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(66), nullable=False)
    yes_ask_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    no_ask_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    estimated_profit_usdc: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("signals.id", ondelete="SET NULL")
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_arb_opps_market_detected", "market_id", "detected_at"),
        Index("idx_arb_opps_executed", "executed"),
    )


# ---------------------------------------------------------------------------
# risk_events — audit trail of every rejection / circuit break.
# ---------------------------------------------------------------------------
class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    signal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("signals.id", ondelete="SET NULL")
    )
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_risk_events_type_created", "event_type", "created_at"),
    )


# ---------------------------------------------------------------------------
# daily_pnl — rolled up at minute cadence by the risk manager.
# ---------------------------------------------------------------------------
class DailyPnl(Base):
    __tablename__ = "daily_pnl"

    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), primary_key=True)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal(0)
    )
    max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=Decimal(0)
    )
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# strategy_state — halt switches; restored on bot restart.
# ---------------------------------------------------------------------------
class StrategyState(Base):
    __tablename__ = "strategy_state"

    strategy_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    is_halted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    halt_reason: Mapped[str | None] = mapped_column(Text)
    halted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    halted_by: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
