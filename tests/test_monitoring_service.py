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

    async def test_update_current_hand_not_initialized(self, mock_db_manager):
        """Test that update_current_hand does nothing when not initialized."""
        service = MonitoringService(mock_db_manager)

        # Should not raise, just return silently
        await service.update_current_hand("table_a", 42)

    async def test_record_hand_grade_not_initialized(self, mock_db_manager):
        """Test that record_hand_grade does nothing when not initialized."""
        service = MonitoringService(mock_db_manager)

        mock_grade = MagicMock()
        # Should not raise, just return silently
        await service.record_hand_grade(1, mock_grade)


class TestRepoProperty:
    """Tests for repo property access."""

    def test_repo_property_raises_when_not_initialized(self, mock_db_manager):
        """Test that accessing repo raises RuntimeError when not initialized."""
        service = MonitoringService(mock_db_manager)

        with pytest.raises(RuntimeError, match="MonitoringService not initialized"):
            _ = service.repo


class TestConnectionAlerts:
    """Tests for connection alert generation."""

    async def test_primary_connection_lost_alert(self, monitoring_service, mock_repo):
        """Test alert when primary connection is lost."""
        # Set up initial connected state
        monitoring_service._table_statuses["table_a"] = {"primary_connected": True}

        with patch.object(
            monitoring_service.alert_manager, "alert_connection_lost"
        ) as mock_alert:
            await monitoring_service.update_table_connection(
                table_id="table_a",
                primary_connected=False,
            )

            mock_alert.assert_called_once_with("table_a", "primary")

    async def test_primary_connection_restored_alert(self, monitoring_service, mock_repo):
        """Test alert when primary connection is restored."""
        # Set up initial disconnected state
        monitoring_service._table_statuses["table_a"] = {"primary_connected": False}

        with patch.object(
            monitoring_service.alert_manager, "alert_connection_restored"
        ) as mock_alert:
            await monitoring_service.update_table_connection(
                table_id="table_a",
                primary_connected=True,
            )

            mock_alert.assert_called_once_with("table_a", "primary")

    async def test_secondary_connection_lost_alert(self, monitoring_service, mock_repo):
        """Test alert when secondary connection is lost."""
        # Set up initial connected state
        monitoring_service._table_statuses["table_a"] = {"secondary_connected": True}

        with patch.object(
            monitoring_service.alert_manager, "alert_connection_lost"
        ) as mock_alert:
            await monitoring_service.update_table_connection(
                table_id="table_a",
                secondary_connected=False,
            )

            mock_alert.assert_called_once_with("table_a", "secondary")

    async def test_secondary_connection_restored_alert(self, monitoring_service, mock_repo):
        """Test alert when secondary connection is restored."""
        # Set up initial disconnected state
        monitoring_service._table_statuses["table_a"] = {"secondary_connected": False}

        with patch.object(
            monitoring_service.alert_manager, "alert_connection_restored"
        ) as mock_alert:
            await monitoring_service.update_table_connection(
                table_id="table_a",
                secondary_connected=True,
            )

            mock_alert.assert_called_once_with("table_a", "secondary")


class TestUpdateCurrentHandErrors:
    """Tests for error handling in update_current_hand."""

    async def test_update_current_hand_handles_exception(
        self, monitoring_service, mock_repo
    ):
        """Test that exceptions are caught and logged."""
        mock_repo.upsert_table_status.side_effect = Exception("DB error")

        # Should not raise, just log error
        await monitoring_service.update_current_hand("table_a", 42)


class TestUpdateFusionResultErrors:
    """Tests for error handling in update_fusion_result."""

    async def test_update_fusion_result_handles_exception(
        self, monitoring_service, mock_repo
    ):
        """Test that exceptions are caught and logged."""
        mock_repo.upsert_table_status.side_effect = Exception("DB error")

        result = FusedHandResult(
            table_id="table_a",
            hand_number=1,
            hand_rank=HandRank.FULL_HOUSE,
            confidence=1.0,
            source=SourceType.PRIMARY,
            primary_result=None,
            secondary_result=None,
            cross_validated=True,
            requires_review=False,
            timestamp=datetime.now(UTC),
        )

        # Should not raise, just log error
        await monitoring_service.update_fusion_result("table_a", result)

    async def test_update_fusion_result_primary_only(self, monitoring_service, mock_repo):
        """Test fusion result update for primary_only case."""
        result = FusedHandResult(
            table_id="table_a",
            hand_number=1,
            hand_rank=HandRank.FULL_HOUSE,
            confidence=1.0,
            source=SourceType.PRIMARY,
            primary_result=None,
            secondary_result=None,
            cross_validated=False,
            requires_review=False,
            timestamp=datetime.now(UTC),
        )

        await monitoring_service.update_fusion_result("table_a", result)

        mock_repo.upsert_table_status.assert_called_once_with(
            table_id="table_a",
            last_fusion_result="primary_only",
        )


class TestHandGradeAlerts:
    """Tests for hand grade alert generation."""

    async def test_grade_a_hand_generates_alert(self, monitoring_service):
        """Test that Grade A hand generates alert."""
        from src.grading.grader import GradeResult

        grade_result = GradeResult(
            grade="A",
            has_premium_hand=True,
            has_long_playtime=True,
            has_premium_board_combo=True,
            conditions_met=3,
            broadcast_eligible=True,
        )

        with patch.object(
            monitoring_service.alert_manager, "alert_grade_a_hand"
        ) as mock_alert:
            await monitoring_service.record_hand_grade(
                hand_id=123,
                grade_result=grade_result,
                table_id="table_a",
                hand_number=42,
            )

            mock_alert.assert_called_once_with(
                table_id="table_a",
                hand_number=42,
                hand_rank="Premium Hand",
                conditions_met=["premium_hand", "long_playtime", "board_combo"],
            )

    async def test_grade_b_hand_no_alert(self, monitoring_service):
        """Test that Grade B hand does not generate alert."""
        from src.grading.grader import GradeResult

        grade_result = GradeResult(
            grade="B",
            has_premium_hand=False,
            has_long_playtime=True,
            has_premium_board_combo=True,
            conditions_met=2,
            broadcast_eligible=True,
        )

        with patch.object(
            monitoring_service.alert_manager, "alert_grade_a_hand"
        ) as mock_alert:
            await monitoring_service.record_hand_grade(
                hand_id=123,
                grade_result=grade_result,
                table_id="table_a",
                hand_number=42,
            )

            mock_alert.assert_not_called()


class TestRecordingSessionAutoId:
    """Tests for recording session auto-generated ID."""

    async def test_start_recording_session_auto_id_format(
        self, monitoring_service, mock_repo
    ):
        """Test that auto-generated session ID has expected format."""
        mock_session = MagicMock()
        mock_session.session_id = None  # Force auto-generation
        mock_repo.create_recording_session.return_value = mock_session

        session_id = await monitoring_service.start_recording_session(
            table_id="table_xyz",
            hand_number=999,
        )

        # Session ID should contain table_id and hand_number
        assert session_id is not None
        assert "table_xyz" in session_id
        assert "999" in session_id


class TestExceptionHandling:
    """Tests for exception handling in various methods."""

    async def test_update_table_connection_handles_exception(
        self, monitoring_service, mock_repo
    ):
        """Test exception handling in update_table_connection."""
        mock_repo.upsert_table_status.side_effect = Exception("DB error")

        # Should not raise
        await monitoring_service.update_table_connection(
            table_id="table_a", primary_connected=True
        )

    async def test_start_recording_session_exception(self, monitoring_service, mock_repo):
        """Test exception handling in start_recording_session."""
        mock_repo.create_recording_session.side_effect = Exception("DB error")

        result = await monitoring_service.start_recording_session("table_a", 42)

        assert result is None

    async def test_start_recording_session_not_initialized(self, mock_db_manager):
        """Test start_recording_session when not initialized."""
        service = MonitoringService(mock_db_manager)

        result = await service.start_recording_session("table_a", 42)

        assert result is None

    async def test_stop_recording_session_not_initialized(self, mock_db_manager):
        """Test stop_recording_session when not initialized."""
        service = MonitoringService(mock_db_manager)

        # Should not raise
        await service.stop_recording_session("table_a")

    async def test_log_health_exception(self, monitoring_service, mock_repo):
        """Test exception handling in log_health."""
        mock_repo.log_health.side_effect = Exception("DB error")

        # Should not raise
        await monitoring_service.log_health("vMix", "connected")


class TestVMixHealthCheck:
    """Tests for vMix health checking."""

    async def test_check_and_log_vmix_health_not_initialized(self, mock_db_manager):
        """Test check_and_log_vmix_health when not initialized."""
        service = MonitoringService(mock_db_manager)
        mock_client = MagicMock()

        # Should not raise
        await service.check_and_log_vmix_health(mock_client)

    async def test_check_and_log_vmix_health_connected(self, monitoring_service, mock_repo):
        """Test check_and_log_vmix_health with successful connection."""
        from src.vmix.client import VMixClient

        mock_client = AsyncMock(spec=VMixClient)
        mock_client.ping = AsyncMock(return_value=True)

        await monitoring_service.check_and_log_vmix_health(mock_client)

        # Should log health
        mock_repo.log_health.assert_called_once()
        call_args = mock_repo.log_health.call_args
        assert call_args.kwargs["service_name"] == "vMix"
        assert call_args.kwargs["status"] == "connected"
        assert call_args.kwargs["latency_ms"] is not None

    async def test_check_and_log_vmix_health_disconnected(
        self, monitoring_service, mock_repo
    ):
        """Test check_and_log_vmix_health with failed connection."""
        from src.vmix.client import VMixClient

        mock_client = AsyncMock(spec=VMixClient)
        mock_client.ping = AsyncMock(return_value=False)

        await monitoring_service.check_and_log_vmix_health(mock_client)

        # Should log health
        mock_repo.log_health.assert_called_once()
        call_args = mock_repo.log_health.call_args
        assert call_args.kwargs["service_name"] == "vMix"
        assert call_args.kwargs["status"] == "disconnected"

    async def test_check_and_log_vmix_health_exception(
        self, monitoring_service, mock_repo
    ):
        """Test check_and_log_vmix_health with exception."""
        from src.vmix.client import VMixClient

        mock_client = AsyncMock(spec=VMixClient)
        mock_client.ping = AsyncMock(side_effect=Exception("Connection error"))

        await monitoring_service.check_and_log_vmix_health(mock_client)

        # Should log error status
        mock_repo.log_health.assert_called_once()
        call_args = mock_repo.log_health.call_args
        assert call_args.kwargs["service_name"] == "vMix"
        assert call_args.kwargs["status"] == "error"

    async def test_check_and_log_vmix_health_wrong_type(
        self, monitoring_service, mock_repo
    ):
        """Test check_and_log_vmix_health with wrong client type."""
        mock_client = MagicMock()  # Not a VMixClient instance

        await monitoring_service.check_and_log_vmix_health(mock_client)

        # Should not log anything
        mock_repo.log_health.assert_not_called()


class TestRecordingFileInfo:
    """Tests for recording file info updates."""

    async def test_update_recording_file_info(self, monitoring_service, mock_repo):
        """Test updating recording file info."""
        # Start a recording session
        mock_session = MagicMock()
        mock_session.session_id = "session_123"
        mock_repo.create_recording_session.return_value = mock_session
        await monitoring_service.start_recording_session("table_a", 42, "session_123")

        # Create recording session object with file info
        from src.recording.session import RecordingSession

        rec_session = RecordingSession(
            table_id="table_a",
            hand_number=42,
            file_path="/path/to/file.mp4",
            file_size_bytes=1024 * 1024 * 256,  # 256 MB
        )

        await monitoring_service.update_recording_file_info(rec_session)

        mock_repo.update_recording_session.assert_called()

    async def test_update_recording_file_info_not_initialized(self, mock_db_manager):
        """Test update_recording_file_info when not initialized."""
        service = MonitoringService(mock_db_manager)

        from src.recording.session import RecordingSession

        rec_session = RecordingSession(
            table_id="table_a",
            hand_number=42,
            file_path="/path/to/file.mp4",
        )

        # Should not raise
        await service.update_recording_file_info(rec_session)

    async def test_update_recording_file_info_no_active_session(
        self, monitoring_service, mock_repo
    ):
        """Test update_recording_file_info when no active session."""
        from src.recording.session import RecordingSession

        rec_session = RecordingSession(
            table_id="table_a",
            hand_number=42,
            file_path="/path/to/file.mp4",
        )

        await monitoring_service.update_recording_file_info(rec_session)

        # Should not update anything
        mock_repo.update_recording_session.assert_not_called()

    async def test_update_recording_file_info_exception(
        self, monitoring_service, mock_repo
    ):
        """Test update_recording_file_info with exception."""
        # Start a recording session
        mock_session = MagicMock()
        mock_session.session_id = "session_123"
        mock_repo.create_recording_session.return_value = mock_session
        await monitoring_service.start_recording_session("table_a", 42, "session_123")

        mock_repo.update_recording_session.side_effect = Exception("DB error")

        from src.recording.session import RecordingSession

        rec_session = RecordingSession(
            table_id="table_a",
            hand_number=42,
            file_path="/path/to/file.mp4",
        )

        # Should not raise
        await monitoring_service.update_recording_file_info(rec_session)
