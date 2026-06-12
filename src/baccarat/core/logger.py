"""Structured logging with trace_id propagation.

All logs are routed through ``structlog``. Two output formats are supported:

* ``json`` — production. One log per line, ``orjson``-encoded, easy to ship
  to Loki / Datadog / CloudWatch.
* ``console`` — local dev. Human-readable with colors.

Every log record automatically carries:

* ``timestamp`` — UTC, ISO 8601 with ms precision.
* ``level`` — DEBUG / INFO / WARNING / ERROR / CRITICAL.
* ``logger`` — the module-level name.
* ``trace_id`` — pulled from the contextvar in :mod:`baccarat.core.trace`,
  if set. This is the single most important field for debugging a misbehaving
  signal — one ``grep`` reconstructs the entire lifecycle.

Initialize once, at process startup:

>>> from baccarat.core.logger import setup_logging
>>> setup_logging(level="INFO", fmt="json", include_trace_id=True)

Then in any module:

>>> import structlog
>>> log = structlog.get_logger(__name__)
>>> log.info("event", market_id="0x…", side="YES")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import orjson
import structlog
from structlog.types import EventDict, Processor

from baccarat.core.trace import current_trace_id


def _add_trace_id(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """structlog processor that injects the current trace_id, if any."""
    tid = current_trace_id()
    if tid is not None:
        event_dict["trace_id"] = tid
    return event_dict


def _orjson_dumps(obj: Any, default: Any = None) -> str:
    """``orjson.dumps`` returns bytes; structlog needs str."""
    return orjson.dumps(obj, default=default).decode("utf-8")


def setup_logging(
    *,
    level: str = "INFO",
    fmt: str = "json",
    include_trace_id: bool = True,
) -> None:
    """Configure structlog + stdlib logging.

    Idempotent: safe to call multiple times (later calls reset the config).
    """
    # 1) stdlib root logger sends everything through a single stream handler.
    #    structlog will format the records.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy libraries unless the user explicitly cranks the level down.
    for noisy in ("websockets", "asyncio", "aiohttp.access", "urllib3", "web3.providers"):
        logging.getLogger(noisy).setLevel(max(root.level, logging.INFO))

    # 2) structlog pipeline.
    pre_chain: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
    ]
    if include_trace_id:
        pre_chain.append(_add_trace_id)
    pre_chain.append(structlog.processors.StackInfoRenderer())
    pre_chain.append(structlog.processors.format_exc_info)

    if fmt == "json":
        renderer: Processor = structlog.processors.JSONRenderer(serializer=_orjson_dumps)
    elif fmt == "console":
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    else:
        raise ValueError(f"Unknown log format: {fmt!r}")

    structlog.configure(
        processors=[*pre_chain, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Convenience wrapper. Modules can also use ``structlog.get_logger`` directly."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
