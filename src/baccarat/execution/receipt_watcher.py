"""Receipt watcher.

Background task that polls :meth:`TxSubmitter.watch_receipt` for every
in-flight tx, decodes the receipt, and updates the matching ``trades`` row
(status, gas_used, block_number, …). Emits PnL events to the risk manager
for daily-drawdown tracking.

Kept separate from :class:`TxSubmitter` so the submission and observation
concerns can scale independently — submitter is short-lived per-call,
watcher is a long-running service.
"""

from __future__ import annotations

from baccarat.core.logger import get_logger
from baccarat.execution.tx_submitter import TxSubmitter
from baccarat.storage.postgres import PostgresClient

log = get_logger(__name__)


class ReceiptWatcher:
    """**M1 stub.**"""

    def __init__(self, submitter: TxSubmitter, db: PostgresClient):
        self._submitter = submitter
        self._db = db

    async def run(self) -> None:
        """Long-running coroutine. Consumes pending tx_hashes and updates trades rows."""
        raise NotImplementedError("ReceiptWatcher.run — implement in M4")
