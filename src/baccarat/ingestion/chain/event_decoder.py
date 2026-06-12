"""Polymarket / ConditionalTokens log decoder.

Wraps :mod:`eth_abi` and a small ABI registry to turn raw ``eth_getLogs`` /
``eth_subscribe`` payloads into structured :class:`OnChainEvent` records.

Supported events (M2 will populate the registry):

* ``OrderFilled`` — Polymarket Exchange (CTF Exchange) — primary copy-trade signal.
* ``PositionSplit`` — ConditionalTokens — user split USDC into Yes + No.
* ``PositionsMerge`` — ConditionalTokens — user merged Yes + No back to USDC.
* ``PayoutRedemption`` — ConditionalTokens — settlement after market resolves.
* ``Transfer`` (ERC20 / ERC1155) — secondary signal for inventory tracking.
"""

from __future__ import annotations

from typing import Any

from baccarat.core.logger import get_logger
from baccarat.core.types import OnChainEvent

log = get_logger(__name__)


class EventDecoder:
    """ABI decoder. **M1 stub.**"""

    def __init__(self) -> None:
        # ABI registry will be loaded from JSON files under ``abis/`` in M2.
        self._abis: dict[str, list[dict[str, Any]]] = {}

    def decode_log(self, raw_log: dict[str, Any]) -> OnChainEvent | None:
        """Return a decoded event, or ``None`` if the log doesn't match a known ABI."""
        raise NotImplementedError("EventDecoder.decode_log — implement in M2")
