"""Application orchestrator.

Single-process, single-event-loop entry point. Wires the modules together,
spawns the long-running pump tasks, and supervises them — if any *critical*
task crashes, the orchestrator initiates a graceful shutdown so the
container can be restarted by the supervisor (Docker / systemd / k8s).

This file is deliberately the only place that knows the full graph of
modules. Each module exposes async entry points; ``main`` connects them
through ``asyncio.Queue``s.

In M1 the wiring is illustrative — the strategies, executor, etc. raise
``NotImplementedError``, so ``main`` itself only sets up infrastructure
and exits cleanly when it discovers there is nothing to run yet. That is
the intended behavior until M2 lands.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import NoReturn

import structlog

from baccarat.core.config import Settings, load_settings
from baccarat.core.logger import setup_logging
from baccarat.core.types import OnChainEvent, OrderBookSnapshot, Signal
from baccarat.storage.postgres import PostgresClient
from baccarat.storage.redis_client import RedisClient

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Queue topology
# ---------------------------------------------------------------------------
class QueueGraph:
    """The four hot-path queues.

    Sizes are bounded so a stalled consumer is detected (queue full → put
    blocks → upstream backs up → we log + alert) instead of OOM-ing.
    """

    def __init__(self) -> None:
        self.market_data: asyncio.Queue[OrderBookSnapshot] = asyncio.Queue(maxsize=10_000)
        self.onchain_events: asyncio.Queue[OnChainEvent] = asyncio.Queue(maxsize=10_000)
        self.signals: asyncio.Queue[Signal] = asyncio.Queue(maxsize=1_000)
        self.orders: asyncio.Queue[Signal] = asyncio.Queue(maxsize=1_000)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
async def _bootstrap_storage(settings: Settings) -> tuple[PostgresClient, RedisClient]:
    pg = PostgresClient.from_url(
        settings.database_url,
        pool_min_size=settings.storage.postgres_pool_min_size,
        pool_max_size=settings.storage.postgres_pool_max_size,
    )
    redis = RedisClient.from_url(
        settings.redis_url,
        decode_responses=settings.storage.redis_decode_responses,
    )

    if not await pg.healthcheck():
        log.error("postgres.unreachable", url=_mask_url(settings.database_url))
        raise SystemExit(2)
    if not await redis.healthcheck():
        log.error("redis.unreachable", url=settings.redis_url)
        raise SystemExit(2)

    log.info("storage.ready")
    return pg, redis


def _mask_url(url: str) -> str:
    """Redact credentials before logging a DSN."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        _, host = rest.split("@", 1)
        return f"{scheme}://***@{host}"
    return url


# ---------------------------------------------------------------------------
# Supervision
# ---------------------------------------------------------------------------
async def _supervise(tasks: list[asyncio.Task[None]], shutdown: asyncio.Event) -> None:
    """Wait for either a shutdown signal or any critical task to die."""
    pending = set(tasks)
    shutdown_task = asyncio.create_task(shutdown.wait(), name="shutdown_waiter")
    pending.add(shutdown_task)

    done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

    for d in done:
        if d is shutdown_task:
            log.info("shutdown.signal_received")
            continue
        exc = d.exception()
        if exc is not None:
            log.error("task.crashed", task=d.get_name(), error=str(exc))
        else:
            log.warning("task.exited_unexpectedly", task=d.get_name())

    # Always cancel the rest to converge on a clean shutdown.
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> int:
    settings = load_settings()
    setup_logging(
        level=settings.logging.level,
        fmt=settings.logging.format,
        include_trace_id=settings.logging.include_trace_id,
    )
    log.info(
        "boot",
        version="0.1.0",
        chain=settings.network.chain,
        dry_run=settings.dry_run,
        rpc_count=len(settings.network.rpc_endpoints),
    )

    pg, redis = await _bootstrap_storage(settings)

    # Shutdown plumbing.
    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    # ---------------------------------------------------------------- M1 stop
    # The remaining wiring (queues + strategies + executor + alert manager)
    # depends on modules that are still stubs. Until M2 lands those modules,
    # we exit cleanly after the storage smoke test so docker-compose treats
    # this as a successful launch instead of a crash loop.
    log.warning(
        "m1.stub_complete",
        message=(
            "Architecture initialized. Module implementations are NotImplementedError "
            "until M2; exiting cleanly so the container does not crash-loop."
        ),
    )

    await pg.close()
    await redis.close()
    return 0

    # The supervision loop below is what main() will look like once M2 ships.
    # Keep the dead code as a wiring spec — easier for reviewers than a diagram.
    # ------------------------------------------------------------------
    # queues = QueueGraph()
    # tasks = [
    #     asyncio.create_task(rpc_pool.health_check_loop(), name="rpc.health"),
    #     asyncio.create_task(_pump_market_data(market_src, queues.market_data, redis), name="pump.market"),
    #     asyncio.create_task(_pump_chain_events(chain_listener, queues.onchain_events), name="pump.chain"),
    #     asyncio.create_task(_run_strategy(arb, queues.market_data, queues.signals), name="strat.arb"),
    #     asyncio.create_task(_run_strategy(copy, queues.onchain_events, queues.signals), name="strat.copy"),
    #     asyncio.create_task(_consume_signals(queues.signals, risk, executor, alert, db), name="exec.consumer"),
    #     asyncio.create_task(receipt_watcher.run(), name="receipt.watcher"),
    #     asyncio.create_task(alert.heartbeat_loop(), name="alert.heartbeat"),
    # ]
    # await _supervise(tasks, shutdown)


def run() -> NoReturn:
    """Console-script entry point. Configured via ``[project.scripts]`` in pyproject."""
    try:
        rc = asyncio.run(main())
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    run()
