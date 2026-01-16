"""Tests for Supabase repository classes."""

from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from src.database.supabase_client import DuplicateSessionError
from src.database.supabase_repository import (
    GFXHandsRepository,
    GFXSessionRepository,
    SyncLogRepository,
)


@pytest.fixture
def mock_supabase():
    """Mock SupabaseManager."""
    manager = MagicMock()
    manager.client = MagicMock()
    manager.execute_with_retry = AsyncMock()
    manager.compute_file_hash = MagicMock(return_value="test_hash")
    return manager


@pytest.fixture
def session_repo(mock_supabase):
    """Create GFXSessionRepository instance."""
    return GFXSessionRepository(mock_supabase)


@pytest.fixture
def hands_repo(mock_supabase):
    """Create GFXHandsRepository instance."""
    return GFXHandsRepository(mock_supabase)


@pytest.fixture
def sync_log_repo(mock_supabase):
    """Create SyncLogRepository instance."""
    return SyncLogRepository(mock_supabase)


@pytest.fixture
def sample_raw_json():
    """Sample PokerGFX JSON data."""
    return {
        "Type": "FEATURE_TABLE",
        "EventTitle": "Test Tournament",
        "SoftwareVersion": "1.0.0",
        "CreatedDateTimeUTC": "2024-01-01T12:00:00Z",
        "Hands": [
            {"ID": 1, "HandNumber": 1, "Players": []},
            {"ID": 2, "HandNumber": 2, "Players": []},
        ],
    }


class TestGFXSessionRepository:
    """Test suite for GFXSessionRepository."""

    async def test_save_session_success(self, session_repo, mock_supabase, sample_raw_json):
        """Test saving a new session successfully."""
        # Mock no existing session
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(data=[])

        # Mock successful insert
        expected_result = {"id": "session-123", "session_id": 123456789}
        mock_supabase.execute_with_retry.return_value = Mock(data=[expected_result])

        result = await session_repo.save_session(
            session_id=123456789,
            file_name="test.json",
            file_hash="abc123",
            raw_json=sample_raw_json,
            nas_path="/nas/test.json"
        )

        assert result == expected_result
        mock_supabase.execute_with_retry.assert_called_once()

    async def test_save_session_duplicate(self, session_repo, mock_supabase, sample_raw_json):
        """Test saving duplicate session returns None."""
        # Mock existing session
        existing_session = {"id": "existing", "file_hash": "abc123"}
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(
            data=[existing_session]
        )

        result = await session_repo.save_session(
            session_id=123456789,
            file_name="test.json",
            file_hash="abc123",
            raw_json=sample_raw_json
        )

        assert result is None
        mock_supabase.execute_with_retry.assert_not_called()

    async def test_save_session_duplicate_error(self, session_repo, mock_supabase, sample_raw_json):
        """Test save session handles DuplicateSessionError."""
        # Mock no existing session in check
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(data=[])

        # Mock duplicate error on insert
        mock_supabase.execute_with_retry.side_effect = DuplicateSessionError("duplicate")

        result = await session_repo.save_session(
            session_id=123456789,
            file_name="test.json",
            file_hash="abc123",
            raw_json=sample_raw_json
        )

        assert result is None

    async def test_get_by_file_hash_found(self, session_repo, mock_supabase):
        """Test getting session by file hash when found."""
        expected_session = {"id": "session-123", "file_hash": "abc123"}
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(
            data=[expected_session]
        )

        result = await session_repo.get_by_file_hash("abc123")

        assert result == expected_session

    async def test_get_by_file_hash_not_found(self, session_repo, mock_supabase):
        """Test getting session by file hash when not found."""
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(data=[])

        result = await session_repo.get_by_file_hash("abc123")

        assert result is None

    async def test_get_by_session_id_found(self, session_repo, mock_supabase):
        """Test getting session by session ID when found."""
        expected_session = {"id": "session-123", "session_id": 123456789}
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(
            data=[expected_session]
        )

        result = await session_repo.get_by_session_id(123456789)

        assert result == expected_session

    async def test_get_by_session_id_not_found(self, session_repo, mock_supabase):
        """Test getting session by session ID when not found."""
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(data=[])

        result = await session_repo.get_by_session_id(123456789)

        assert result is None

    async def test_list_recent_sessions(self, session_repo, mock_supabase):
        """Test listing recent sessions."""
        expected_sessions = [
            {"id": "1", "table_type": "FEATURE_TABLE"},
            {"id": "2", "table_type": "MAIN_TABLE"},
        ]
        mock_supabase.client.table().select().order().limit().execute.return_value = Mock(
            data=expected_sessions
        )

        result = await session_repo.list_recent_sessions(limit=50)

        assert result == expected_sessions

    async def test_list_recent_sessions_filtered(self, session_repo, mock_supabase):
        """Test listing recent sessions with table type filter."""
        expected_sessions = [{"id": "1", "table_type": "FEATURE_TABLE"}]
        mock_chain = MagicMock()
        mock_chain.execute.return_value = Mock(data=expected_sessions)
        mock_supabase.client.table().select().order().limit().eq.return_value = mock_chain

        result = await session_repo.list_recent_sessions(limit=50, table_type="FEATURE_TABLE")

        assert result == expected_sessions

    async def test_get_session_hands(self, session_repo, mock_supabase):
        """Test getting hands from session."""
        hands = [{"ID": 1}, {"ID": 2}]
        raw_json = {"Hands": hands}
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(
            data=[{"raw_json": raw_json}]
        )

        result = await session_repo.get_session_hands("session-123")

        assert result == hands

    async def test_get_session_hands_not_found(self, session_repo, mock_supabase):
        """Test getting hands from non-existent session."""
        mock_supabase.client.table().select().eq().limit().execute.return_value = Mock(data=[])

        result = await session_repo.get_session_hands("session-123")

        assert result == []

    async def test_update_session_success(self, session_repo, mock_supabase, sample_raw_json):
        """Test updating session successfully."""
        expected_result = {"id": "session-123", "session_id": 123456789}
        mock_supabase.execute_with_retry.return_value = Mock(data=[expected_result])

        result = await session_repo.update_session(
            session_id=123456789,
            raw_json=sample_raw_json,
            file_hash="new_hash"
        )

        assert result == expected_result

    async def test_update_session_not_found(self, session_repo, mock_supabase, sample_raw_json):
        """Test updating non-existent session."""
        mock_supabase.execute_with_retry.return_value = Mock(data=[])

        result = await session_repo.update_session(
            session_id=123456789,
            raw_json=sample_raw_json,
            file_hash="new_hash"
        )

        assert result is None

    async def test_update_session_error(self, session_repo, mock_supabase, sample_raw_json):
        """Test update session handles errors."""
        mock_supabase.execute_with_retry.side_effect = Exception("Database error")

        result = await session_repo.update_session(
            session_id=123456789,
            raw_json=sample_raw_json,
            file_hash="new_hash"
        )

        assert result is None


class TestGFXHandsRepository:
    """Test suite for GFXHandsRepository."""

    async def test_save_hands_success(self, hands_repo, mock_supabase):
        """Test saving hands successfully."""
        hands = [
            {"ID": 1, "HandNumber": 1, "Players": [], "CommunityCards": []},
            {"ID": 2, "HandNumber": 2, "Players": [{"Name": "Player1"}], "CommunityCards": []},
        ]
        expected_result = [{"id": "hand-1"}, {"id": "hand-2"}]
        mock_supabase.execute_with_retry.return_value = Mock(data=expected_result)

        result = await hands_repo.save_hands(session_id=123456789, hands=hands)

        assert result == expected_result
        mock_supabase.execute_with_retry.assert_called_once()

    async def test_save_hands_empty_list(self, hands_repo, mock_supabase):
        """Test saving empty hands list."""
        result = await hands_repo.save_hands(session_id=123456789, hands=[])

        assert result == []
        mock_supabase.execute_with_retry.assert_not_called()

    async def test_save_hands_missing_id(self, hands_repo, mock_supabase):
        """Test save hands skips hands without ID."""
        hands = [
            {"ID": 1, "HandNumber": 1, "Players": []},
            {"HandNumber": 2, "Players": []},  # Missing ID
        ]
        mock_supabase.execute_with_retry.return_value = Mock(data=[{"id": "hand-1"}])

        result = await hands_repo.save_hands(session_id=123456789, hands=hands)

        assert len(result) == 1

    async def test_save_hands_error(self, hands_repo, mock_supabase):
        """Test save hands handles errors."""
        hands = [{"ID": 1, "HandNumber": 1, "Players": []}]
        mock_supabase.execute_with_retry.side_effect = Exception("Database error")

        result = await hands_repo.save_hands(session_id=123456789, hands=hands)

        assert result == []

    async def test_get_existing_hand_ids(self, hands_repo, mock_supabase):
        """Test getting existing hand IDs."""
        mock_supabase.client.table().select().eq().execute.return_value = Mock(
            data=[{"hand_id": 1}, {"hand_id": 2}, {"hand_id": 3}]
        )

        result = await hands_repo.get_existing_hand_ids(session_id=123456789)

        assert result == {1, 2, 3}

    async def test_get_existing_hand_ids_empty(self, hands_repo, mock_supabase):
        """Test getting existing hand IDs when empty."""
        mock_supabase.client.table().select().eq().execute.return_value = Mock(data=[])

        result = await hands_repo.get_existing_hand_ids(session_id=123456789)

        assert result == set()

    async def test_get_new_hands(self, hands_repo, mock_supabase):
        """Test filtering new hands."""
        # Mock existing hands
        mock_supabase.client.table().select().eq().execute.return_value = Mock(
            data=[{"hand_id": 1}, {"hand_id": 2}]
        )

        all_hands = [
            {"ID": 1, "HandNumber": 1},  # Existing
            {"ID": 2, "HandNumber": 2},  # Existing
            {"ID": 3, "HandNumber": 3},  # New
            {"ID": 4, "HandNumber": 4},  # New
        ]

        result = await hands_repo.get_new_hands(session_id=123456789, all_hands=all_hands)

        assert len(result) == 2
        assert result[0]["ID"] == 3
        assert result[1]["ID"] == 4

    async def test_get_new_hands_all_new(self, hands_repo, mock_supabase):
        """Test getting new hands when all are new."""
        mock_supabase.client.table().select().eq().execute.return_value = Mock(data=[])

        all_hands = [{"ID": 1}, {"ID": 2}]

        result = await hands_repo.get_new_hands(session_id=123456789, all_hands=all_hands)

        assert len(result) == 2

    async def test_get_hands_by_session(self, hands_repo, mock_supabase):
        """Test getting hands by session."""
        expected_hands = [{"id": "hand-1"}, {"id": "hand-2"}]
        mock_supabase.client.table().select().eq().order().limit().execute.return_value = Mock(
            data=expected_hands
        )

        result = await hands_repo.get_hands_by_session(session_id=123456789, limit=100)

        assert result == expected_hands

    async def test_get_recent_hands(self, hands_repo, mock_supabase):
        """Test getting recent hands."""
        expected_hands = [{"id": "hand-1"}, {"id": "hand-2"}]
        mock_supabase.client.table().select().order().limit().execute.return_value = Mock(
            data=expected_hands
        )

        result = await hands_repo.get_recent_hands(limit=50)

        assert result == expected_hands

    async def test_count_hands_by_session(self, hands_repo, mock_supabase):
        """Test counting hands by session."""
        mock_supabase.client.table().select().eq().execute.return_value = Mock(count=42)

        result = await hands_repo.count_hands_by_session(session_id=123456789)

        assert result == 42

    async def test_count_hands_by_session_zero(self, hands_repo, mock_supabase):
        """Test counting hands when none exist."""
        mock_supabase.client.table().select().eq().execute.return_value = Mock(count=None)

        result = await hands_repo.count_hands_by_session(session_id=123456789)

        assert result == 0


class TestSyncLogRepository:
    """Test suite for SyncLogRepository."""

    async def test_log_sync_start(self, sync_log_repo, mock_supabase):
        """Test logging sync start."""
        expected_log = {
            "id": "log-123",
            "file_name": "test.json",
            "status": "processing"
        }
        mock_supabase.client.table().insert().execute.return_value = Mock(
            data=[expected_log]
        )

        result = await sync_log_repo.log_sync_start(
            file_name="test.json",
            file_path="/path/test.json",
            file_hash="abc123",
            file_size_bytes=1024,
            operation="created"
        )

        assert result == expected_log

    async def test_log_sync_complete_success(self, sync_log_repo, mock_supabase):
        """Test logging sync completion with success."""
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = Mock(data=[])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update
        mock_supabase.client.table.return_value = mock_table

        await sync_log_repo.log_sync_complete(
            log_id="log-123",
            session_id="session-456",
            status="success"
        )

        # Verify update was called
        mock_table.update.assert_called_once()

    async def test_log_sync_complete_failed(self, sync_log_repo, mock_supabase):
        """Test logging sync completion with failure."""
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()
        mock_eq.execute.return_value = Mock(data=[])
        mock_update.eq.return_value = mock_eq
        mock_table.update.return_value = mock_update
        mock_supabase.client.table.return_value = mock_table

        await sync_log_repo.log_sync_complete(
            log_id="log-123",
            status="failed",
            error_message="Network timeout"
        )

        # Verify update was called
        mock_table.update.assert_called_once()

    async def test_is_file_processed_true(self, sync_log_repo, mock_supabase):
        """Test checking if file is processed returns true."""
        mock_supabase.client.table().select().eq().eq().limit().execute.return_value = Mock(
            data=[{"id": "log-123"}]
        )

        result = await sync_log_repo.is_file_processed("abc123")

        assert result is True

    async def test_is_file_processed_false(self, sync_log_repo, mock_supabase):
        """Test checking if file is processed returns false."""
        mock_supabase.client.table().select().eq().eq().limit().execute.return_value = Mock(
            data=[]
        )

        result = await sync_log_repo.is_file_processed("abc123")

        assert result is False

    async def test_get_recent_logs(self, sync_log_repo, mock_supabase):
        """Test getting recent logs."""
        expected_logs = [{"id": "log-1"}, {"id": "log-2"}]
        mock_supabase.client.table().select().order().limit().execute.return_value = Mock(
            data=expected_logs
        )

        result = await sync_log_repo.get_recent_logs(limit=100)

        assert result == expected_logs

    async def test_get_recent_logs_filtered(self, sync_log_repo, mock_supabase):
        """Test getting recent logs filtered by status."""
        expected_logs = [{"id": "log-1", "status": "success"}]
        mock_chain = MagicMock()
        mock_chain.execute.return_value = Mock(data=expected_logs)
        mock_supabase.client.table().select().order().limit().eq.return_value = mock_chain

        result = await sync_log_repo.get_recent_logs(limit=100, status="success")

        assert result == expected_logs

    async def test_get_failed_syncs(self, sync_log_repo, mock_supabase):
        """Test getting failed syncs."""
        expected_logs = [{"id": "log-1", "status": "failed"}]
        mock_supabase.client.table().select().eq().order().limit().execute.return_value = Mock(
            data=expected_logs
        )

        result = await sync_log_repo.get_failed_syncs(limit=50)

        assert result == expected_logs

    async def test_increment_retry_count(self, sync_log_repo, mock_supabase):
        """Test incrementing retry count."""
        # Mock for select query
        mock_select_table = MagicMock()
        mock_select_result = MagicMock()
        mock_select_result.execute.return_value = Mock(data=[{"retry_count": 2}])
        mock_select_table.select().eq().limit.return_value = mock_select_result

        # Mock for update query
        mock_update_table = MagicMock()
        mock_update_chain = MagicMock()
        mock_update_chain.execute.return_value = Mock(data=[])
        mock_update_table.update().eq.return_value = mock_update_chain

        # Use side_effect to return different mocks for each table() call
        mock_supabase.client.table.side_effect = [mock_select_table, mock_update_table]

        await sync_log_repo.increment_retry_count("log-123")

        # Verify both select and update were called
        assert mock_supabase.client.table.call_count == 2

    async def test_increment_retry_count_none(self, sync_log_repo, mock_supabase):
        """Test incrementing retry count from None."""
        # Mock for select query
        mock_select_table = MagicMock()
        mock_select_result = MagicMock()
        mock_select_result.execute.return_value = Mock(data=[{"retry_count": None}])
        mock_select_table.select().eq().limit.return_value = mock_select_result

        # Mock for update query
        mock_update_table = MagicMock()
        mock_update_chain = MagicMock()
        mock_update_chain.execute.return_value = Mock(data=[])
        mock_update_table.update().eq.return_value = mock_update_chain

        # Use side_effect to return different mocks for each table() call
        mock_supabase.client.table.side_effect = [mock_select_table, mock_update_table]

        await sync_log_repo.increment_retry_count("log-123")

        # Verify both select and update were called
        assert mock_supabase.client.table.call_count == 2
