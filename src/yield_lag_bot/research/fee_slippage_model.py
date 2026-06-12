"""Simple cost model defaults for M1 research reports."""

from __future__ import annotations


def estimate_cost_bps(*, fee_bps: float = 5.0, slippage_bps: float = 2.0) -> tuple[float, float]:
    return fee_bps, slippage_bps
