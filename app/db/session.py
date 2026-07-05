"""
Async database session management using SQLAlchemy 2.0.

Provides:
- Async engine creation
- Async session factory
- FastAPI dependency for getting DB sessions
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import ssl

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

from app.core.config import settings

# Remove sslmode and channel_binding from URL if present
database_url = settings.database_url_async.replace("?sslmode=require&channel_binding=require", "")

# Setup SSL context for asyncpg
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={
        "ssl": ssl_context,
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session.

    Yields:
        An async SQLAlchemy session, automatically closed after use.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
