"""
Database connection management using SQLAlchemy async engine.
Supports both PostgreSQL (production) and SQLite (local development).
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalise the database URL for async drivers
# ---------------------------------------------------------------------------
_raw_url = settings.DATABASE_URL

if _raw_url.startswith("postgresql://") or _raw_url.startswith("postgres://"):
    # Use asyncpg for PostgreSQL
    _async_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _async_url = _async_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("sqlite:///"):
    # Use aiosqlite for SQLite
    _async_url = _raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
else:
    _async_url = _raw_url

# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------
engine = create_async_engine(
    _async_url,
    echo=settings.APP_DEBUG,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


async def init_db() -> None:
    """Create all tables on startup (development convenience)."""
    from app.models.database import Ticket, Response  # noqa: F401 – register models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
