"""Core infrastructure: config, logging, exceptions, common types, trace_id."""

from baccarat.core.exceptions import (
    BaccaratError,
    ConfigError,
    ExecutionError,
    HedgeFailedError,
    IngestionError,
    RiskRejectError,
    RpcError,
    StrategyError,
)
from baccarat.core.trace import (
    bind_trace_id,
    current_trace_id,
    new_trace_id,
    use_trace_id,
)
from baccarat.core.types import (
    ExecutionResult,
    MarketInfo,
    OnChainEvent,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderType,
    Position,
    Side,
    Signal,
    SignalSource,
    SignalStatus,
    TimeInForce,
    Trade,
    TradeStatus,
)

__all__ = [
    # exceptions
    "BaccaratError",
    "ConfigError",
    "ExecutionError",
    "HedgeFailedError",
    "IngestionError",
    "RiskRejectError",
    "RpcError",
    "StrategyError",
    # trace
    "bind_trace_id",
    "current_trace_id",
    "new_trace_id",
    "use_trace_id",
    # types
    "ExecutionResult",
    "MarketInfo",
    "OnChainEvent",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "OrderType",
    "Position",
    "Side",
    "Signal",
    "SignalSource",
    "SignalStatus",
    "TimeInForce",
    "Trade",
    "TradeStatus",
]
