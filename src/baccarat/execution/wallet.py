"""Wallet — private key + ERC-20 approval management.

Holds the private key in memory exactly once at startup. All signing flows
through this object so we have a single audit point.

Operational notes (M4)
----------------------
* On startup, log the wallet address but NEVER the key.
* USDC approve: check allowance for ``polymarket.exchange_address`` and
  ``polymarket.ctf_address``; bump to ``2**256 - 1`` only if the operator
  explicitly opts in, otherwise prefer per-batch approve.
* All chain interactions go through the :class:`RpcPool` so failover works.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import SecretStr

from baccarat.core.logger import get_logger
from baccarat.ingestion.chain.rpc_pool import RpcPool

log = get_logger(__name__)


class Wallet:
    """Owns the private key and signs everything. **M1 stub.**"""

    def __init__(self, private_key: SecretStr, rpc_pool: RpcPool):
        self._key = private_key  # never expose .get_secret_value() outside this class
        self._rpc = rpc_pool
        self._address: str | None = None  # populated lazily; matches sender of every tx

    @property
    def address(self) -> str:
        raise NotImplementedError("Wallet.address — implement in M4")

    async def get_usdc_balance(self) -> Decimal:
        raise NotImplementedError("Wallet.get_usdc_balance — implement in M4")

    async def ensure_approval(self, spender: str, min_amount: Decimal) -> None:
        """Approve ``spender`` to spend at least ``min_amount`` USDC."""
        raise NotImplementedError("Wallet.ensure_approval — implement in M4")

    def sign_eip712(self, typed_data: dict[str, Any]) -> str:
        """Used for CLOB order signing. Returns 0x-prefixed signature."""
        raise NotImplementedError("Wallet.sign_eip712 — implement in M4")

    async def sign_and_send_tx(self, tx: dict[str, Any]) -> str:
        """Sign + broadcast. Returns tx hash. Caller owns nonce management."""
        raise NotImplementedError("Wallet.sign_and_send_tx — implement in M4")
