"""Kill switch primitive."""

from __future__ import annotations


class KillSwitch:
    def __init__(self, *, on_error: bool = True) -> None:
        self.on_error = on_error
        self.tripped = False
        self.reason: str | None = None

    def trip(self, reason: str) -> None:
        self.tripped = True
        self.reason = reason
