"""Telegram alerter.

Triggers (M3 / M4)
------------------
* ``CRITICAL`` — :class:`HedgeFailedError`, manual intervention required.
* ``ERROR`` — N consecutive on-chain failures (config:
  ``alerting.alert_on_consecutive_failures``).
* ``WARNING`` — risk circuit broken (daily drawdown), strategy halted.
* ``INFO`` — large arbitrage success (above a threshold), heartbeat.

Implementation notes
--------------------
* Use ``aiogram.Bot`` with the bot token from settings; rate-limit per
  Telegram's 30 msg/sec global ceiling.
* Format messages with the trace_id at the top so an operator can grep
  logs immediately.
* Never block the trading hot path — ``send`` enqueues to an internal
  queue consumed by a dedicated task.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from baccarat.core.config import AlertingSettings
from baccarat.core.logger import get_logger

log = get_logger(__name__)


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertManager:
    """**M1 stub.**"""

    def __init__(self, settings: AlertingSettings):
        self._settings = settings

    async def start(self) -> None:
        """Start the background sender task."""
        raise NotImplementedError("AlertManager.start — implement in M3")

    async def stop(self) -> None:
        raise NotImplementedError("AlertManager.stop — implement in M3")

    async def send(
        self,
        severity: AlertSeverity,
        message: str,
        **fields: Any,
    ) -> None:
        """Enqueue an alert. Non-blocking; never raises."""
        raise NotImplementedError("AlertManager.send — implement in M3")

    async def heartbeat_loop(self) -> None:
        """Background coroutine: posts an "alive" message every heartbeat_interval_sec."""
        raise NotImplementedError("AlertManager.heartbeat_loop — implement in M3")
