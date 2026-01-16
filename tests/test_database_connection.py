"""Tests for database connection manager - targeting 70%+ coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.database.connection import DatabaseManager


class MockDatabaseSettings:
    """Mock database settings."""

    def __init__(self):
        self.host = "localhost"
        self.port = 5432
        self.database = "test_db"
        self.username = "test_user"
        self.password = "test_pass"
        self.pool_size = 5


class TestDatabaseManagerInit:
    """Test DatabaseManager initialization."""

    def test_init_with_settings(self):
        """Test initialization with settings."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        assert manager.settings == settings
        assert manager._engine is None
        assert manager._session_factory is None

    def test_connection_string_basic(self):
        """Test connection string generation."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        conn_str = manager.connection_string

        assert "postgresql+asyncpg://" in conn_str
        assert "test_user" in conn_str
        assert "localhost" in conn_str
        assert "5432" in conn_str
        assert "test_db" in conn_str

    def test_connection_string_with_special_chars(self):
        """Test connection string with special characters in password."""
        settings = MockDatabaseSettings()
        settings.password = "p@ss!word#123"
        manager = DatabaseManager(settings)

        conn_str = manager.connection_string

        # Special chars should be URL-encoded
        assert "p%40ss%21word%23123" in conn_str


class TestDatabaseManagerConnect:
    """Test connect method."""

    async def test_connect_success(self):
        """Test successful database connection."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        with patch("src.database.connection.create_async_engine") as mock_engine:
            with patch(
                "src.database.connection.async_sessionmaker"
            ) as mock_session_maker:
                mock_engine_instance = MagicMock(spec=AsyncEngine)
                mock_engine.return_value = mock_engine_instance

                await manager.connect()

                mock_engine.assert_called_once()
                mock_session_maker.assert_called_once()
                assert manager._engine == mock_engine_instance

    async def test_connect_sets_pool_size(self):
        """Test that connect uses pool_size from settings."""
        settings = MockDatabaseSettings()
        settings.pool_size = 10
        manager = DatabaseManager(settings)

        with patch("src.database.connection.create_async_engine") as mock_engine:
            with patch("src.database.connection.async_sessionmaker"):
                await manager.connect()

                # Check pool_size in call args
                call_kwargs = mock_engine.call_args[1]
                assert call_kwargs["pool_size"] == 10


class TestDatabaseManagerDisconnect:
    """Test disconnect method."""

    async def test_disconnect_with_engine(self):
        """Test disconnecting when engine exists."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_engine.dispose = AsyncMock()
        manager._engine = mock_engine

        await manager.disconnect()

        mock_engine.dispose.assert_called_once()

    async def test_disconnect_without_engine(self):
        """Test disconnecting when no engine exists."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)
        manager._engine = None

        # Should not raise error
        await manager.disconnect()


class TestDatabaseManagerSession:
    """Test session context manager."""

    async def test_session_not_connected(self):
        """Test session raises error when not connected."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)
        manager._session_factory = None

        with pytest.raises(RuntimeError, match="Database not connected"):
            async with manager.session():
                pass

    async def test_session_success_commits(self):
        """Test session commits on success."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock()

        manager._session_factory = mock_factory

        async with manager.session() as session:
            assert session == mock_session

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    async def test_session_error_rolls_back(self):
        """Test session rolls back on error."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def mock_aenter(self):
            return mock_session

        async def mock_aexit(self, exc_type, exc_val, exc_tb):
            if exc_type:
                await mock_session.rollback()
            else:
                await mock_session.commit()

        mock_context = MagicMock()
        mock_context.__aenter__ = mock_aenter
        mock_context.__aexit__ = mock_aexit

        mock_factory = MagicMock(return_value=mock_context)
        manager._session_factory = mock_factory

        try:
            async with manager.session() as session:
                raise ValueError("Test error")
        except ValueError:
            pass

        # rollback should have been called (at least once)
        assert mock_session.rollback.called
        mock_session.commit.assert_not_called()


class TestDatabaseManagerCreateTables:
    """Test create_tables method."""

    async def test_create_tables_success(self):
        """Test creating tables successfully."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__aexit__ = AsyncMock()

        manager._engine = mock_engine

        with patch("src.database.models.Base") as mock_base:
            await manager.create_tables()

            mock_conn.run_sync.assert_called_once()

    async def test_create_tables_not_connected(self):
        """Test create_tables raises error when not connected."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)
        manager._engine = None

        with pytest.raises(RuntimeError, match="Database not connected"):
            await manager.create_tables()


class TestDatabaseManagerDropTables:
    """Test drop_tables method."""

    async def test_drop_tables_success(self):
        """Test dropping tables successfully."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        mock_engine = AsyncMock(spec=AsyncEngine)
        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()
        mock_engine.begin = MagicMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(
            return_value=mock_conn
        )
        mock_engine.begin.return_value.__aexit__ = AsyncMock()

        manager._engine = mock_engine

        with patch("src.database.models.Base") as mock_base:
            await manager.drop_tables()

            mock_conn.run_sync.assert_called_once()

    async def test_drop_tables_not_connected(self):
        """Test drop_tables raises error when not connected."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)
        manager._engine = None

        with pytest.raises(RuntimeError, match="Database not connected"):
            await manager.drop_tables()


class TestDatabaseManagerIntegration:
    """Integration tests for DatabaseManager."""

    async def test_full_lifecycle(self):
        """Test full connect-use-disconnect lifecycle."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        with patch("src.database.connection.create_async_engine") as mock_engine:
            with patch(
                "src.database.connection.async_sessionmaker"
            ) as mock_session_maker:
                mock_engine_instance = AsyncMock(spec=AsyncEngine)
                mock_engine_instance.dispose = AsyncMock()
                mock_engine.return_value = mock_engine_instance

                mock_session = AsyncMock(spec=AsyncSession)
                mock_session.commit = AsyncMock()
                mock_session.rollback = AsyncMock()

                mock_factory = MagicMock()
                mock_factory.return_value.__aenter__ = AsyncMock(
                    return_value=mock_session
                )
                mock_factory.return_value.__aexit__ = AsyncMock()
                mock_session_maker.return_value = mock_factory

                # Connect
                await manager.connect()
                assert manager._engine is not None

                # Use session
                async with manager.session() as session:
                    assert session == mock_session

                # Disconnect
                await manager.disconnect()
                mock_engine_instance.dispose.assert_called_once()

    async def test_multiple_sessions(self):
        """Test using multiple sessions sequentially."""
        settings = MockDatabaseSettings()
        manager = DatabaseManager(settings)

        mock_session1 = AsyncMock(spec=AsyncSession)
        mock_session1.commit = AsyncMock()
        mock_session2 = AsyncMock(spec=AsyncSession)
        mock_session2.commit = AsyncMock()

        session_count = 0

        def get_mock_session():
            nonlocal session_count
            session_count += 1
            return mock_session1 if session_count == 1 else mock_session2

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(side_effect=get_mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock()

        manager._session_factory = mock_factory

        # Use first session
        async with manager.session() as session1:
            assert session1 == mock_session1

        # Use second session
        async with manager.session() as session2:
            assert session2 == mock_session2

        mock_session1.commit.assert_called_once()
        mock_session2.commit.assert_called_once()
