"""Tests for Supabase client management."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.database.supabase_client import (
    DuplicateSessionError,
    SupabaseError,
    SupabaseManager,
    SyncFailedError,
)


@pytest.fixture
def mock_settings():
    """Mock Supabase settings."""
    settings = Mock()
    settings.url = "https://test.supabase.co"
    settings.key = "test-api-key"
    settings.max_retries = 3
    settings.retry_delay = 0.1
    settings.timeout = 30
    return settings


@pytest.fixture
def mock_settings_invalid():
    """Mock invalid Supabase settings."""
    settings = Mock()
    settings.url = None
    settings.key = None
    settings.max_retries = 3
    settings.retry_delay = 0.1
    settings.timeout = 30
    return settings


@pytest.fixture
def manager(mock_settings):
    """Create SupabaseManager instance."""
    return SupabaseManager(mock_settings)


class TestSupabaseManager:
    """Test suite for SupabaseManager."""

    def test_init(self, mock_settings):
        """Test manager initialization."""
        manager = SupabaseManager(mock_settings)
        assert manager.settings == mock_settings
        assert manager._client is None

    @patch("src.database.supabase_client.create_client")
    def test_client_property_creates_client(self, mock_create_client, mock_settings):
        """Test client property creates client on first access."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        manager = SupabaseManager(mock_settings)
        client = manager.client

        assert client == mock_client
        mock_create_client.assert_called_once_with(
            mock_settings.url,
            mock_settings.key,
        )

    @patch("src.database.supabase_client.create_client")
    def test_client_property_caches_client(self, mock_create_client, mock_settings):
        """Test client property returns cached client on subsequent access."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        manager = SupabaseManager(mock_settings)
        client1 = manager.client
        client2 = manager.client

        assert client1 is client2
        mock_create_client.assert_called_once()

    def test_client_property_raises_on_missing_config(self, mock_settings_invalid):
        """Test client property raises error when config is missing."""
        manager = SupabaseManager(mock_settings_invalid)

        with pytest.raises(SupabaseError, match="Supabase URL and KEY must be configured"):
            _ = manager.client

    async def test_execute_with_retry_success_first_attempt(self, manager):
        """Test execute_with_retry succeeds on first attempt."""
        operation = Mock(return_value="success")

        result = await manager.execute_with_retry(operation)

        assert result == "success"
        operation.assert_called_once()

    async def test_execute_with_retry_success_after_retries(self, manager):
        """Test execute_with_retry succeeds after retries."""
        operation = Mock(side_effect=[
            Exception("Network error"),
            Exception("Timeout"),
            "success"
        ])

        result = await manager.execute_with_retry(operation)

        assert result == "success"
        assert operation.call_count == 3

    async def test_execute_with_retry_raises_duplicate_error(self, manager):
        """Test execute_with_retry raises DuplicateSessionError immediately."""
        operation = Mock(side_effect=Exception("duplicate key violation"))

        with pytest.raises(DuplicateSessionError, match="duplicate key violation"):
            await manager.execute_with_retry(operation)

        operation.assert_called_once()

    async def test_execute_with_retry_raises_duplicate_unique_error(self, manager):
        """Test execute_with_retry raises DuplicateSessionError for unique constraint."""
        operation = Mock(side_effect=Exception("UNIQUE constraint failed"))

        with pytest.raises(DuplicateSessionError, match="UNIQUE constraint failed"):
            await manager.execute_with_retry(operation)

        operation.assert_called_once()

    async def test_execute_with_retry_exhausts_retries(self, manager):
        """Test execute_with_retry raises SyncFailedError after all retries."""
        operation = Mock(side_effect=Exception("Network error"))

        with pytest.raises(SyncFailedError, match="Operation failed after 3 attempts"):
            await manager.execute_with_retry(operation)

        assert operation.call_count == 3

    async def test_execute_with_retry_exponential_backoff(self, manager):
        """Test execute_with_retry uses exponential backoff."""
        operation = Mock(side_effect=[
            Exception("Error 1"),
            Exception("Error 2"),
            "success"
        ])

        start = asyncio.get_event_loop().time()
        await manager.execute_with_retry(operation)
        elapsed = asyncio.get_event_loop().time() - start

        # Should wait 0.1s + 0.2s = 0.3s minimum (allow small timing variance)
        assert elapsed >= 0.29

    def test_compute_file_hash(self):
        """Test file hash computation."""
        content1 = b"test content"
        content2 = b"different content"
        content3 = b"test content"

        hash1 = SupabaseManager.compute_file_hash(content1)
        hash2 = SupabaseManager.compute_file_hash(content2)
        hash3 = SupabaseManager.compute_file_hash(content3)

        assert hash1 == hash3
        assert hash1 != hash2
        assert len(hash1) == 64  # SHA256 hex length

    @patch("src.database.supabase_client.create_client")
    async def test_health_check_success(self, mock_create_client, mock_settings):
        """Test health check passes when connection is healthy."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value.limit.return_value.execute.return_value = Mock(data=[])
        mock_create_client.return_value = mock_client

        manager = SupabaseManager(mock_settings)
        result = await manager.health_check()

        assert result is True
        mock_client.table.assert_called_once_with("gfx_sessions")

    @patch("src.database.supabase_client.create_client")
    async def test_health_check_failure(self, mock_create_client, mock_settings):
        """Test health check fails when connection error occurs."""
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Connection failed")
        mock_create_client.return_value = mock_client

        manager = SupabaseManager(mock_settings)
        result = await manager.health_check()

        assert result is False

    async def test_close(self, manager):
        """Test close resets client connection."""
        manager._client = MagicMock()

        await manager.close()

        assert manager._client is None

    @patch("src.database.supabase_client.create_client")
    def test_get_stats_connected(self, mock_create_client, mock_settings):
        """Test get_stats returns correct stats when connected."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        manager = SupabaseManager(mock_settings)
        _ = manager.client  # Trigger connection

        stats = manager.get_stats()

        assert stats["url"] == mock_settings.url
        assert stats["connected"] is True
        assert stats["max_retries"] == 3
        assert stats["timeout"] == 30

    def test_get_stats_disconnected(self, manager):
        """Test get_stats returns correct stats when disconnected."""
        stats = manager.get_stats()

        assert stats["url"] == manager.settings.url
        assert stats["connected"] is False
        assert stats["max_retries"] == 3
        assert stats["timeout"] == 30


class TestSupabaseExceptions:
    """Test Supabase exception hierarchy."""

    def test_supabase_error_is_exception(self):
        """Test SupabaseError is an Exception."""
        error = SupabaseError("test error")
        assert isinstance(error, Exception)

    def test_duplicate_session_error_is_supabase_error(self):
        """Test DuplicateSessionError inherits from SupabaseError."""
        error = DuplicateSessionError("duplicate")
        assert isinstance(error, SupabaseError)
        assert isinstance(error, Exception)

    def test_sync_failed_error_is_supabase_error(self):
        """Test SyncFailedError inherits from SupabaseError."""
        error = SyncFailedError("sync failed")
        assert isinstance(error, SupabaseError)
        assert isinstance(error, Exception)
