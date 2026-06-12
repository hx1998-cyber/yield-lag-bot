"""Transaction builder.

Prepares unsigned transaction dicts ready for :meth:`Wallet.sign_and_send_tx`.
The two transaction types we care about for M4:

* ``ConditionalTokens.mergePositions(...)`` — closes a Yes+No pair into 1 USDC.
* ``ConditionalTokens.redeemPositions(...)`` — claims winnings after market resolution.
* ``ERC20.approve(spender, amount)`` — only when allowance check fails.

CLOB orders are NOT transactions — they're EIP-712 typed-data signatures
signed by :meth:`Wallet.sign_eip712` and posted to the REST API.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from baccarat.core.logger import get_logger

log = get_logger(__name__)


class TxBuilder:
    """**M1 stub.**"""

    def __init__(self, ctf_address: str, usdc_address: str, exchange_address: str):
        self._ctf = ctf_address
        self._usdc = usdc_address
        self._exchange = exchange_address

    def build_merge(
        self,
        condition_id: str,
        amount: Decimal,
        *,
        from_address: str,
        nonce: int,
        gas_units: int,
        max_fee_per_gas_wei: int,
        max_priority_fee_per_gas_wei: int,
    ) -> dict[str, Any]:
        raise NotImplementedError("TxBuilder.build_merge — implement in M4")

    def build_redeem(
        self,
        condition_id: str,
        index_sets: list[int],
        *,
        from_address: str,
        nonce: int,
        gas_units: int,
        max_fee_per_gas_wei: int,
        max_priority_fee_per_gas_wei: int,
    ) -> dict[str, Any]:
        raise NotImplementedError("TxBuilder.build_redeem — implement in M4")

    def build_approve(
        self,
        spender: str,
        amount: Decimal,
        *,
        from_address: str,
        nonce: int,
        gas_units: int,
        max_fee_per_gas_wei: int,
        max_priority_fee_per_gas_wei: int,
    ) -> dict[str, Any]:
        raise NotImplementedError("TxBuilder.build_approve — implement in M4")
