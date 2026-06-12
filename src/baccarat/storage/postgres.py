"""Async Postgres client.

Single ``AsyncEngine`` per process. Sessions are short-lived — open one,
use it inside an ``async with``, commit, close. Long-lived sessions hold
connections from the pool and starve other tasks; never share a session
across tasks.

Use the ``session()`` async-context-manager for one-off work, or hand
the factory to a service that needs to open many sessions.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from baccarat.core.logger import get_logger

log = get_logger(__name__)


class PostgresClient:
    """Owns the engine + session factory. Construct once at startup."""

    def __init__(self, engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]):
        self._engine = engine
        self._session_factory = session_factory

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        pool_min_size: int = 2,
        pool_max_size: int = 10,
        echo: bool = False,
    ) -> PostgresClient:
        """Build a client from a DSN. Driver MUST be ``postgresql+asyncpg``."""
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "PostgresClient requires asyncpg; got "
                f"{url.split('://', 1)[0]}"
            )
        engine = create_async_engine(
            url,
            echo=echo,
            pool_size=pool_max_size,
            max_overflow=0,
            pool_pre_ping=True,
            # asyncpg keeps connections; min size enforced by pre-warming on startup.
            pool_recycle=300,
        )
        factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        client = cls(engine, factory)
        client._pool_min_size = pool_min_size  # used by warmup()  # noqa: SLF001
        return client

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """One-shot session. Commits on clean exit, rolls back on any exception."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def healthcheck(self) -> bool:
        """SELECT 1. Returns True iff the engine is reachable."""
        from sqlalchemy import text

        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            log.warning("postgres.healthcheck.failed", error=str(exc))
            return False
        return True

    async def close(self) -> None:
        await self._engine.dispose()
