"""Database connection management using SQLAlchemy async."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from src.config.settings import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages async PostgreSQL connections using SQLAlchemy."""

    def __init__(self, settings: "DatabaseSettings"):
        self.settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def connection_string(self) -> str:
        """Build async PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.settings.username}:{self.settings.password}"
            f"@{self.settings.host}:{self.settings.port}/{self.settings.database}"
        )

    async def connect(self) -> None:
        """Initialize database connection."""
        db_info = f"{self.settings.host}:{self.settings.port}/{self.settings.database}"
        logger.info(f"Connecting to database: {db_info}")

        self._engine = create_async_engine(
            self.connection_string,
            pool_size=self.settings.pool_size,
            echo=False,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info("Database connection established")

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connection closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session context manager."""
        if not self._session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_tables(self) -> None:
        """Create all tables (for development/testing)."""
        from src.database.models import Base

        if not self._engine:
            raise RuntimeError("Database not connected. Call connect() first.")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created")

    async def drop_tables(self) -> None:
        """Drop all tables (for testing only)."""
        from src.database.models import Base

        if not self._engine:
            raise RuntimeError("Database not connected. Call connect() first.")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            logger.info("Database tables dropped")
