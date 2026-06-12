"""initial schema

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20

Creates the full M1 schema in a single migration. Subsequent changes go in
new revisions — never edit this file after it's merged.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260520_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ markets
    op.create_table(
        "markets",
        sa.Column("condition_id", sa.String(66), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("yes_token_id", sa.String(78), nullable=False),
        sa.Column("no_token_id", sa.String(78), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_markets_status", "markets", ["status"])

    # ------------------------------------------------- smart_money_addresses
    op.create_table(
        "smart_money_addresses",
        sa.Column("address", sa.String(42), primary_key=True),
        sa.Column("label", sa.String(100)),
        sa.Column("copy_ratio", sa.Numeric(10, 6)),
        sa.Column("fixed_size_usdc", sa.Numeric(20, 6)),
        sa.Column("max_slippage_bps", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(copy_ratio IS NOT NULL) OR (fixed_size_usdc IS NOT NULL)",
            name="ck_smart_money_size_specified",
        ),
    )
    op.create_index(
        "idx_smart_money_enabled", "smart_money_addresses", ["enabled"]
    )

    # ------------------------------------------------------------------ signals
    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("strategy_name", sa.String(50), nullable=False),
        sa.Column("market_id", sa.String(66), nullable=False),
        sa.Column("token_id", sa.String(78), nullable=False),
        sa.Column("side", sa.String(3)),
        sa.Column("order_type", sa.String(10)),
        sa.Column("size_usdc", sa.Numeric(20, 6)),
        sa.Column("limit_price", sa.Numeric(10, 6)),
        sa.Column("expected_profit_usdc", sa.Numeric(20, 6)),
        sa.Column("time_in_force", sa.String(5), nullable=False, server_default="GTC"),
        sa.Column("expire_at_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("leg_role", sa.String(10), nullable=False, server_default="SOLO"),
        sa.Column(
            "parent_signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("reject_reason", sa.Text()),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_signals_status_created", "signals", ["status", "created_at"])
    op.create_index("idx_signals_market", "signals", ["market_id"])
    op.create_index("idx_signals_parent", "signals", ["parent_signal_id"])

    # ------------------------------------------------------------------- trades
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("leg_role", sa.String(10), nullable=False, server_default="SOLO"),
        sa.Column("clob_order_id", sa.String(100), unique=True),
        sa.Column("tx_hash", sa.String(66), unique=True),
        sa.Column("nonce", sa.BigInteger()),
        sa.Column("block_number", sa.BigInteger()),
        sa.Column("requested_size_usdc", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "filled_size_usdc",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("requested_price", sa.Numeric(10, 6)),
        sa.Column("average_price", sa.Numeric(10, 6)),
        sa.Column(
            "fee_paid_usdc",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("gas_used", sa.BigInteger()),
        sa.Column("gas_price_wei", sa.Numeric(30, 0)),
        sa.Column("gas_cost_usdc", sa.Numeric(20, 6)),
        sa.Column("realized_pnl_usdc", sa.Numeric(20, 6)),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("filled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "filled_size_usdc <= requested_size_usdc",
            name="ck_trades_fill_le_request",
        ),
    )
    op.create_index(
        "idx_trades_status_submitted", "trades", ["status", "submitted_at"]
    )
    op.create_index("idx_trades_signal", "trades", ["signal_id"])

    # ---------------------------------------------------------------- positions
    op.create_table(
        "positions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("market_id", sa.String(66), nullable=False),
        sa.Column("token_id", sa.String(78), nullable=False),
        sa.Column("side", sa.String(3), nullable=False),
        sa.Column("current_size", sa.Numeric(20, 6), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(10, 6), nullable=False),
        sa.Column("cost_basis_usdc", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "unrealized_pnl_usdc",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_mark_price", sa.Numeric(10, 6)),
        sa.Column("last_mark_at", sa.DateTime(timezone=True)),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("market_id", "token_id", name="uq_positions_market_token"),
    )
    op.create_index("idx_positions_market", "positions", ["market_id"])

    # ---------------------------------------------------- arbitrage_opportunities
    op.create_table(
        "arbitrage_opportunities",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("market_id", sa.String(66), nullable=False),
        sa.Column("yes_ask_price", sa.Numeric(10, 6), nullable=False),
        sa.Column("no_ask_price", sa.Numeric(10, 6), nullable=False),
        sa.Column("total_cost", sa.Numeric(10, 6), nullable=False),
        sa.Column("estimated_profit_usdc", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "executed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_arb_opps_market_detected",
        "arbitrage_opportunities",
        ["market_id", "detected_at"],
    )
    op.create_index(
        "idx_arb_opps_executed", "arbitrage_opportunities", ["executed"]
    )

    # -------------------------------------------------------------- risk_events
    op.create_table(
        "risk_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
        ),
        sa.Column("details", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_risk_events_type_created", "risk_events", ["event_type", "created_at"]
    )

    # --------------------------------------------------------------- daily_pnl
    op.create_table(
        "daily_pnl",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column(
            "realized_pnl",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_drawdown",
            sa.Numeric(20, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ----------------------------------------------------------- strategy_state
    op.create_table(
        "strategy_state",
        sa.Column("strategy_name", sa.String(50), primary_key=True),
        sa.Column(
            "is_halted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("halt_reason", sa.Text()),
        sa.Column("halted_at", sa.DateTime(timezone=True)),
        sa.Column("halted_by", sa.String(50)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("strategy_state")
    op.drop_table("daily_pnl")
    op.drop_index("idx_risk_events_type_created", table_name="risk_events")
    op.drop_table("risk_events")
    op.drop_index("idx_arb_opps_executed", table_name="arbitrage_opportunities")
    op.drop_index("idx_arb_opps_market_detected", table_name="arbitrage_opportunities")
    op.drop_table("arbitrage_opportunities")
    op.drop_index("idx_positions_market", table_name="positions")
    op.drop_table("positions")
    op.drop_index("idx_trades_signal", table_name="trades")
    op.drop_index("idx_trades_status_submitted", table_name="trades")
    op.drop_table("trades")
    op.drop_index("idx_signals_parent", table_name="signals")
    op.drop_index("idx_signals_market", table_name="signals")
    op.drop_index("idx_signals_status_created", table_name="signals")
    op.drop_table("signals")
    op.drop_index("idx_smart_money_enabled", table_name="smart_money_addresses")
    op.drop_table("smart_money_addresses")
    op.drop_index("idx_markets_status", table_name="markets")
    op.drop_table("markets")
