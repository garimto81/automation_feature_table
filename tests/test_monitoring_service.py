"""Tests for MonitoringService (PRD-0008 Phase 2.2)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dashboard.monitoring_service import MonitoringService
from src.models.hand import FusedHandResult, HandRank, SourceType


@pytest.fixture
def mock_db_manager():
    """Create a mock DatabaseManager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_repo():
    """Create a mock MonitoringRepository."""
    repo = MagicMock()
    repo.upsert_table_status = AsyncMock()
    repo.create_recording_session = AsyncMock()
    repo.update_recording_session = AsyncMock()
    repo.log_health = AsyncMock()
    repo.get_all_table_statuses = AsyncMock(return_value=[])
    repo.get_grade_distribution = AsyncMock(return_value={})
    repo.get_active_recording_sessions = AsyncMock(return_value=[])
    repo.get_all_latest_health = AsyncMock(return_value={})
    repo.get_today_stats = AsyncMock(return_value={})
    return repo


@pytest.fixture
def monitoring_service(mock_db_manager, mock_repo):
    """Create a MonitoringService with mocked dependencies."""
    service = MonitoringService(mock_db_manager, mock_repo)
    service._initialized = True
    return service


class TestMonitoringServiceInit:
    """Tests for MonitoringService initialization."""

    def test_init_defaults(self, mock_db_manager):
        """Test initialization with defaults."""
        service = MonitoringService(mock_db_manager)

        assert service.db_manager == mock_db_manager
        assert service._repo is None
        assert service._initialized is False
        assert service._table_statuses == {}
        assert service._active_recordings == {}

    async def test_initialize_creates_repo(self, mock_db_manager):
        """Test initialize creates repository."""
        service = MonitoringService(mock_db_manager)

        with patch("src.database.monitoring_repository.MonitoringRepository") as mock_class:
            mock_class.return_value = MagicMock()
            await service.initialize()

            assert service._initialized is True

    async def test_initialize_skips_if_already_initialized(self, monitoring_service):
        """Test initialize skips if already initialized."""
        original_repo = monitoring_service._repo
        await monitoring_service.initialize()

        # Repo should be unchanged
        assert monitoring_service._repo is original_repo


class TestTableConnectionUpdates:
    """Tests for table connection status updates."""

    async def test_update_table_connection_primary(self, monitoring_service, mock_repo):
        """Test updating primary connection status."""
        await monitoring_service.update_table_connection(
            table_id="table_a",
            primary_connected=True,
        )

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_a",
            primary_connected=True,
            secondary_connected=None,
        )

    async def test_update_table_connection_secondary(self, monitoring_service, mock_repo):
        """Test updating secondary connection status."""
        await monitoring_service.update_table_connection(
            table_id="table_b",
            secondary_connected=True,
        )

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_b",
            primary_connected=None,
            secondary_connected=True,
        )

    async def test_update_table_connection_both(self, monitoring_service, mock_repo):
        """Test updating both connection statuses."""
        await monitoring_service.update_table_connection(
            table_id="table_c",
            primary_connected=True,
            secondary_connected=True,
        )

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_c",
            primary_connected=True,
            secondary_connected=True,
        )

    async def test_update_table_connection_updates_cache(self, monitoring_service, mock_repo):
        """Test that connection update also updates internal cache."""
        await monitoring_service.update_table_connection(
            table_id="table_a",
            primary_connected=True,
        )

        assert monitoring_service._table_statuses["table_a"]["primary_connected"] is True


class TestCurrentHandUpdates:
    """Tests for current hand updates."""

    async def test_update_current_hand(self, monitoring_service, mock_repo):
        """Test updating current hand information."""
        start_time = datetime.now(UTC)

        await monitoring_service.update_current_hand(
            table_id="table_a",
            hand_number=42,
            hand_start_time=start_time,
        )

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_a",
            current_hand_number=42,
            hand_start_time=start_time,
        )

    async def test_update_current_hand_auto_timestamp(self, monitoring_service, mock_repo):
        """Test that missing timestamp is auto-generated."""
        await monitoring_service.update_current_hand(
            table_id="table_a",
            hand_number=42,
        )

        call_args = mock_repo.upsert_table_status.call_args
        assert call_args.kwargs["hand_start_time"] is not None


class TestFusionResultUpdates:
    """Tests for fusion result updates."""

    def _create_fused_result(
        self,
        cross_validated: bool = False,
        requires_review: bool = False,
        source: SourceType = SourceType.PRIMARY,
    ) -> FusedHandResult:
        """Helper to create FusedHandResult for testing."""
        return FusedHandResult(
            table_id="table_a",
            hand_number=1,
            hand_rank=HandRank.FULL_HOUSE,
            confidence=1.0,
            source=source,
            primary_result=None,
            secondary_result=None,
            cross_validated=cross_validated,
            requires_review=requires_review,
            timestamp=datetime.now(UTC),
        )

    async def test_update_fusion_result_validated(self, monitoring_service, mock_repo):
        """Test fusion result update for validated case."""
        result = self._create_fused_result(cross_validated=True)

        await monitoring_service.update_fusion_result("table_a", result)

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_a",
            last_fusion_result="validated",
        )

    async def test_update_fusion_result_review(self, monitoring_service, mock_repo):
        """Test fusion result update for review case."""
        result = self._create_fused_result(requires_review=True)

        await monitoring_service.update_fusion_result("table_a", result)

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_a",
            last_fusion_result="review",
        )

    async def test_update_fusion_result_fallback(self, monitoring_service, mock_repo):
        """Test fusion result update for fallback case."""
        result = self._create_fused_result(source=SourceType.SECONDARY)

        await monitoring_service.update_fusion_result("table_a", result)

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_a",
            last_fusion_result="fallback",
        )


class TestRecordingSessionUpdates:
    """Tests for recording session updates."""

    async def test_start_recording_session(self, monitoring_service, mock_repo):
        """Test starting a recording session."""
        mock_session = MagicMock()
        mock_session.session_id = "custom_session_id"
        mock_repo.create_recording_session.return_value = mock_session

        session_id = await monitoring_service.start_recording_session(
            table_id="table_a",
            hand_number=42,
            session_id="custom_session_id",
        )

        assert session_id == "custom_session_id"
        assert monitoring_service._active_recordings["table_a"] == "custom_session_id"
        mock_repo.create_recording_session.assert_called_once()

    async def test_start_recording_session_auto_id(self, monitoring_service, mock_repo):
        """Test auto-generated session ID."""
        mock_session = MagicMock()
        mock_repo.create_recording_session.return_value = mock_session

        session_id = await monitoring_service.start_recording_session(
            table_id="table_a",
            hand_number=42,
        )

        assert session_id is not None
        assert "table_a" in session_id
        assert "42" in session_id

    async def test_stop_recording_session(self, monitoring_service, mock_repo):
        """Test stopping a recording session."""
        monitoring_service._active_recordings["table_a"] = "session_123"

        await monitoring_service.stop_recording_session(
            table_id="table_a",
            file_path="/path/to/file.mp4",
            file_size_mb=256.5,
        )

        assert "table_a" not in monitoring_service._active_recordings
        mock_repo.update_recording_session.assert_called_once()
        call_args = mock_repo.update_recording_session.call_args
        assert call_args.kwargs["session_id"] == "session_123"
        assert call_args.kwargs["status"] == "completed"
        assert call_args.kwargs["file_path"] == "/path/to/file.mp4"
        assert call_args.kwargs["file_size_mb"] == 256.5

    async def test_stop_recording_session_no_active(self, monitoring_service, mock_repo):
        """Test stopping when no active session exists."""
        await monitoring_service.stop_recording_session(table_id="table_a")

        mock_repo.update_recording_session.assert_not_called()


class TestHealthLogging:
    """Tests for health logging."""

    async def test_log_health(self, monitoring_service, mock_repo):
        """Test logging health status."""
        await monitoring_service.log_health(
            service_name="PostgreSQL",
            status="connected",
            latency_ms=12,
            message="All good",
        )

        mock_repo.log_health.assert_called_once_with(
            service_name="PostgreSQL",
            status="connected",
            latency_ms=12,
            message="All good",
        )


class TestBatchOperations:
    """Tests for batch operations."""

    async def test_sync_all_table_statuses(self, monitoring_service, mock_repo):
        """Test syncing all table statuses."""
        await monitoring_service.sync_all_table_statuses(
            table_ids=["table_a", "table_b", "table_c"],
            primary_connected=True,
            secondary_connected=False,
        )

        assert mock_repo.upsert_table_status.call_count == 3

    async def test_get_dashboard_state(self, monitoring_service, mock_repo):
        """Test getting dashboard state."""
        state = await monitoring_service.get_dashboard_state()

        assert "table_statuses" in state
        assert "grade_distribution" in state
        assert "recording_sessions" in state
        assert "system_health" in state
        assert "today_stats" in state
        assert "last_updated" in state


class TestNotInitialized:
    """Tests for behavior when service is not initialized."""

    async def test_update_table_connection_not_initialized(self, mock_db_manager):
        """Test that update does nothing when not initialized."""
        service = MonitoringService(mock_db_manager)

        # Should not raise, just return silently
        await service.update_table_connection("table_a", primary_connected=True)

    async def test_log_health_not_initialized(self, mock_db_manager):
        """Test that log_health does nothing when not initialized."""
        service = MonitoringService(mock_db_manager)

        # Should not raise, just return silently
        await service.log_health("test", "connected")

    async def test_get_dashboard_state_not_initialized(self, mock_db_manager):
        """Test that get_dashboard_state returns empty dict when not initialized."""
        service = MonitoringService(mock_db_manager)

        result = await service.get_dashboard_state()

        assert result == {}
