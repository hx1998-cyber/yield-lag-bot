"""M1 smoke tests — verify the scaffolding wires up correctly.

Real functional tests land in M3 (strategies) and M4 (execution).
"""

from __future__ import annotations

import time
from decimal import Decimal

from baccarat.core.types import (
    LegRole,
    OrderType,
    Side,
    Signal,
    SignalSource,
    SignalStatus,
    TimeInForce,
)


def test_signal_dataclass_defaults() -> None:
    sig = Signal(
        source=SignalSource.ARBITRAGE,
        strategy_name="arbitrage",
        market_id="0x" + "ab" * 32,
        token_id="123",
        side=Side.YES,
        order_type=OrderType.LIMIT,
        size_usdc=Decimal("100"),
        limit_price=Decimal("0.45"),
        max_slippage_bps=20,
        expected_profit_usdc=Decimal("1.5"),
    )
    assert sig.status is SignalStatus.PENDING
    assert sig.time_in_force is TimeInForce.GTC
    assert sig.leg_role is LegRole.SOLO
    assert sig.expire_at_ms == 0
    assert sig.is_expired() is False
    assert sig.trace_id.startswith("tmp-")


def test_signal_expiry() -> None:
    now_ms = int(time.time() * 1000)
    sig = Signal(
        source=SignalSource.COPY_TRADE,
        strategy_name="copy_trade",
        market_id="0x" + "cd" * 32,
        token_id="456",
        side=Side.NO,
        order_type=OrderType.LIMIT,
        size_usdc=Decimal("50"),
        limit_price=Decimal("0.55"),
        max_slippage_bps=50,
        expected_profit_usdc=Decimal("0"),
        expire_at_ms=now_ms - 1,
    )
    assert sig.is_expired(now_ms) is True


def test_trace_id_uses_signal_id_when_assigned() -> None:
    sig = Signal(
        source=SignalSource.ARBITRAGE,
        strategy_name="arbitrage",
        market_id="0x" + "ef" * 32,
        token_id="789",
        side=Side.YES,
        order_type=OrderType.MARKET,
        size_usdc=Decimal("10"),
        limit_price=Decimal("0.5"),
        max_slippage_bps=30,
        expected_profit_usdc=Decimal("0.6"),
        id=42,
    )
    assert sig.trace_id == "sig-42"
