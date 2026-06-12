"""Verify the trace_id contextvar propagates correctly."""

from __future__ import annotations

import asyncio

from baccarat.core.trace import (
    bind_trace_id,
    current_trace_id,
    new_trace_id,
    reset_trace_id,
    use_trace_id,
)


def test_new_trace_id_is_unique() -> None:
    a = new_trace_id()
    b = new_trace_id()
    assert a != b
    assert a.startswith("tmp-")


def test_use_trace_id_sets_and_resets() -> None:
    assert current_trace_id() is None
    with use_trace_id("sig-1"):
        assert current_trace_id() == "sig-1"
    assert current_trace_id() is None


def test_use_trace_id_nested() -> None:
    with use_trace_id("outer"):
        assert current_trace_id() == "outer"
        with use_trace_id("inner"):
            assert current_trace_id() == "inner"
        assert current_trace_id() == "outer"


def test_bind_and_reset_explicit() -> None:
    token = bind_trace_id("manual-1")
    try:
        assert current_trace_id() == "manual-1"
    finally:
        reset_trace_id(token)
    assert current_trace_id() is None


async def _child(expected: str) -> str | None:
    # contextvars copy across await; must see the bound trace id.
    await asyncio.sleep(0)
    return current_trace_id()


def test_trace_id_propagates_across_await() -> None:
    async def runner() -> None:
        with use_trace_id("sig-99"):
            seen = await _child("sig-99")
            assert seen == "sig-99"

    asyncio.run(runner())
