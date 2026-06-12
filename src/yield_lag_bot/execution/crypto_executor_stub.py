"""No real crypto order placement in M1."""

from __future__ import annotations


class CryptoExecutorStub:
    def __init__(self, *, live_trading: bool = False, has_credentials: bool = False) -> None:
        self.live_trading = live_trading
        self.has_credentials = has_credentials

    async def place_order(self, *args, **kwargs) -> None:
        if not self.live_trading:
            raise RuntimeError("live trading is disabled; M1 supports paper orders only")
        if not self.has_credentials:
            raise RuntimeError("missing exchange credentials; live order placement is unavailable")
        raise NotImplementedError("real crypto order placement is prohibited in M1")
