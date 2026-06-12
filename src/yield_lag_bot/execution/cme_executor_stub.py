"""No CME order placement in M1."""

from __future__ import annotations


class CMEExecutorStub:
    async def place_order(self, *args, **kwargs) -> None:
        raise RuntimeError("CME live order placement is prohibited in M1")
