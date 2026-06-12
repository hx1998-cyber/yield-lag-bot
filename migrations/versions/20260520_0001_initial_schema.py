"""Project YIELD-LAG M1 schema

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20
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
    op.create_table(
        "market_ticks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("instrument_type", sa.Text(), nullable=False),
        sa.Column("exchange_ts", sa.DateTime(timezone=True)),
        sa.Column("receive_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("process_ts", sa.DateTime(timezone=True)),
        sa.Column("bid_price", sa.Numeric()),
        sa.Column("ask_price", sa.Numeric()),
        sa.Column("bid_size", sa.Numeric()),
        sa.Column("ask_size", sa.Numeric()),
        sa.Column("last_price", sa.Numeric()),
        sa.Column("sequence_id", sa.Text()),
        sa.Column("raw_payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_ticks_symbol_time "
        "ON market_ticks(symbol, receive_ts DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_ticks_venue_symbol_time "
        "ON market_ticks(venue, symbol, receive_ts DESC)"
    )

    op.create_table(
        "latency_stats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange_ts", sa.DateTime(timezone=True)),
        sa.Column("receive_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("process_ts", sa.DateTime(timezone=True)),
        sa.Column("receive_delay_ms", sa.Numeric()),
        sa.Column("process_delay_ms", sa.Numeric()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("signal_name", sa.Text(), nullable=False),
        sa.Column("cme_symbol", sa.Text(), nullable=False),
        sa.Column("crypto_symbol", sa.Text(), nullable=False),
        sa.Column("window_ms", sa.Integer(), nullable=False),
        sa.Column("horizon_ms", sa.Integer(), nullable=False),
        sa.Column("signal_value", sa.Numeric(), nullable=False),
        sa.Column("predicted_side", sa.Text()),
        sa.Column("confidence", sa.Numeric()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.BigInteger(), sa.ForeignKey("signals.id")),
        sa.Column("venue", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("qty", sa.Numeric(), nullable=False),
        sa.Column("fee", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("slippage", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="simulated"),
        sa.Column("pnl", sa.Numeric()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("paper_orders")
    op.drop_table("signals")
    op.drop_table("latency_stats")
    op.drop_index("idx_market_ticks_venue_symbol_time", table_name="market_ticks")
    op.drop_index("idx_market_ticks_symbol_time", table_name="market_ticks")
    op.drop_table("market_ticks")
