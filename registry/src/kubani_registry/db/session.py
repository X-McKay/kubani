"""Database session management for the registry service."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """Get the database engine."""
    global _engine
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory."""
    global _session_factory
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


async def init_db(database_url: str, echo: bool = False) -> None:
    """
    Initialize the database connection.

    Args:
        database_url: PostgreSQL connection string (asyncpg format)
        echo: Whether to echo SQL statements
    """
    global _engine, _session_factory

    # Convert postgresql:// to postgresql+asyncpg://
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("Database URL must start with postgresql:// or postgresql+asyncpg://")

    logger.info(f"Initializing database connection to {database_url.split('@')[-1]}")

    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info("Database connection initialized")


async def close_db() -> None:
    """Close the database connection."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection closed")


async def create_tables() -> None:
    """Create all tables in the database."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session.

    Use as a dependency in FastAPI:
        @app.get("/agents")
        async def list_agents(session: AsyncSession = Depends(get_session)):
            ...

    Or as an async context manager:
        async with get_session() as session:
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session as an async context manager.

    Example:
        async with session_context() as session:
            result = await session.execute(select(Agent))
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
