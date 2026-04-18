"""SQLAlchemy async engine and session factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().environment == "development",
    pool_pre_ping=True,
)

_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for FastAPI dependency injection."""
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for DB sessions outside FastAPI DI."""
    async with _session_factory() as session:
        yield session


async def get_engine() -> object:
    """Return the async engine for migrations and setup."""
    return _engine
