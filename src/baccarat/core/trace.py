"""Trace ID propagation.

Every signal that enters the pipeline gets a trace_id (typically the signal's
DB id, falling back to a UUID before the row exists). The id lives in a
``contextvars.ContextVar`` so that any code running on the same task — or any
sub-task spawned from it — sees the same id. The structlog processor in
:mod:`baccarat.core.logger` reads this var and injects ``trace_id`` into every
log record automatically.

Usage
-----

Synchronous block:

>>> from baccarat.core.trace import use_trace_id, new_trace_id
>>> with use_trace_id(new_trace_id()):
...     log.info("starting risk check")

Async block (same API — ContextVar is task-local):

>>> async with use_trace_id_async("sig-42"):
...     await risk.check(signal)

Manual binding (for code that crosses framework boundaries):

>>> bind_trace_id("sig-42")  # NOT recommended; prefer the context manager
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

_TRACE_ID: ContextVar[str | None] = ContextVar("baccarat_trace_id", default=None)


def new_trace_id() -> str:
    """Return a freshly minted trace id (used until a DB-assigned id exists)."""
    return f"tmp-{uuid.uuid4().hex[:12]}"


def current_trace_id() -> str | None:
    """Return the trace id currently bound on this async task, or ``None``."""
    return _TRACE_ID.get()


def bind_trace_id(trace_id: str) -> Token[str | None]:
    """Set the trace id and return the reset token. Caller is responsible for resetting.

    Prefer :func:`use_trace_id` over this — it can't leak.
    """
    return _TRACE_ID.set(trace_id)


def reset_trace_id(token: Token[str | None]) -> None:
    """Reset the trace id using the token returned by :func:`bind_trace_id`."""
    _TRACE_ID.reset(token)


@contextmanager
def use_trace_id(trace_id: str) -> Iterator[str]:
    """Context manager that binds ``trace_id`` and restores the previous value on exit.

    Works for both sync and async code (contextvars are task-local, so awaiting
    inside the ``with`` block keeps the binding).
    """
    token = _TRACE_ID.set(trace_id)
    try:
        yield trace_id
    finally:
        _TRACE_ID.reset(token)
