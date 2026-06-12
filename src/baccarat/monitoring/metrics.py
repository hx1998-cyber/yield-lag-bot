"""Lightweight metrics collector.

For M1 we keep this as a thin facade so the rest of the codebase can call
``metrics.incr("signals.emitted", strategy="arbitrage")`` without committing
to a backend. M2+ may wire this to Prometheus / OpenTelemetry / a custom
Postgres rollup; for now everything is logged at DEBUG.
"""

from __future__ import annotations

from typing import Any

from baccarat.core.logger import get_logger

log = get_logger(__name__)


class MetricsCollector:
    def incr(self, name: str, value: int = 1, **tags: Any) -> None:
        log.debug("metric.incr", name=name, value=value, **tags)

    def observe(self, name: str, value: float, **tags: Any) -> None:
        log.debug("metric.observe", name=name, value=value, **tags)


# Module-level singleton for convenience. Replace via dependency injection in tests.
metrics = MetricsCollector()
