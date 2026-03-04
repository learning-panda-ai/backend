"""
Async SQLAlchemy engine, session factory, and declarative base.

Engine and session factory are created lazily so that importing this module
in test environments (where DATABASE_URL may be absent) does not immediately
raise a configuration error.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _build_engine() -> "AsyncEngine | None":
    if not settings.DATABASE_URL:
        return None
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


_engine = _build_engine()

_session_factory: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    if _engine is not None
    else None
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async DB session.
    Commits on success; rolls back on any exception.
    Raises HTTP 503 when DATABASE_URL is not configured.
    """
    if _session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured.",
        )
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
