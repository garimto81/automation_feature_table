"""Tests for MonitoringService (PRD-0008 Phase 2)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.dashboard.monitoring_service import (
    Alert,
    AlertType,
    MonitoringService,
)


@pytest.fixture
def mock_repo():
    """Create a mock MonitoringRepository."""
    repo = AsyncMock()
    repo.upsert_table_status = AsyncMock()
    repo.create_recording_session = AsyncMock()
    repo.update_recording_session = AsyncMock()
    repo.log_health = AsyncMock()
    return repo


@pytest.fixture
def service(mock_repo):
    """Create a MonitoringService with mock repository."""
    return MonitoringService(monitoring_repo=mock_repo)


class TestAlertDataclass:
    """Tests for Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            alert_type=AlertType.PRIMARY_DISCONNECTED,
            table_id="table_a",
            message="Primary disconnected",
        )

        assert alert.alert_type == AlertType.PRIMARY_DISCONNECTED
        assert alert.table_id == "table_a"
        assert alert.message == "Primary disconnected"
        assert isinstance(alert.timestamp, datetime)

    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = Alert(
            alert_type=AlertType.A_GRADE_HAND,
            table_id="table_b",
            message="A-Grade hand!",
            details={"hand_number": 42},
        )

        result = alert.to_dict()

        assert result["type"] == "a_grade_hand"
        assert result["table_id"] == "table_b"
        assert result["message"] == "A-Grade hand!"
        assert result["details"] == {"hand_number": 42}
        assert "timestamp" in result


class TestAlertType:
    """Tests for AlertType enum."""

    def test_alert_types(self):
        """Test all alert types exist."""
        assert AlertType.PRIMARY_DISCONNECTED.value == "primary_disconnected"
        assert AlertType.SECONDARY_DISCONNECTED.value == "secondary_disconnected"
        assert AlertType.PRIMARY_RECONNECTED.value == "primary_reconnected"
        assert AlertType.SECONDARY_RECONNECTED.value == "secondary_reconnected"
        assert AlertType.A_GRADE_HAND.value == "a_grade_hand"
        assert AlertType.RECORDING_ERROR.value == "recording_error"
        assert AlertType.SYSTEM_ERROR.value == "system_error"


class TestMonitoringServiceTableStatus:
    """Tests for table status updates."""

    async def test_update_table_status(self, service, mock_repo):
        """Test updating table status."""
        await service.update_table_status(
            table_id="table_a",
            primary_connected=True,
            secondary_connected=True,
        )

        mock_repo.upsert_table_status.assert_called_once()
        call_kwargs = mock_repo.upsert_table_status.call_args.kwargs
        assert call_kwargs["table_id"] == "table_a"
        assert call_kwargs["primary_connected"] is True
        assert call_kwargs["secondary_connected"] is True

    async def test_primary_disconnect_triggers_alert(self, service, mock_repo):
        """Test that primary disconnect triggers an alert."""
        alerts_received = []

        def capture_alert(alert):
            alerts_received.append(alert)

        service.set_alert_callback(capture_alert)

        # First call to establish state
        await service.update_table_status("table_a", primary_connected=True)

        # Second call with disconnect
        await service.update_table_status("table_a", primary_connected=False)

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == AlertType.PRIMARY_DISCONNECTED
        assert alerts_received[0].table_id == "table_a"

    async def test_primary_reconnect_triggers_alert(self, service, mock_repo):
        """Test that primary reconnect triggers an alert."""
        alerts_received = []
        service.set_alert_callback(lambda a: alerts_received.append(a))

        # Establish disconnected state
        await service.update_table_status("table_a", primary_connected=False)
        # Reconnect
        await service.update_table_status("table_a", primary_connected=True)

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == AlertType.PRIMARY_RECONNECTED

    async def test_secondary_disconnect_triggers_alert(self, service, mock_repo):
        """Test that secondary disconnect triggers an alert."""
        alerts_received = []
        service.set_alert_callback(lambda a: alerts_received.append(a))

        await service.update_table_status("table_b", secondary_connected=True)
        await service.update_table_status("table_b", secondary_connected=False)

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == AlertType.SECONDARY_DISCONNECTED

    async def test_clear_current_hand(self, service, mock_repo):
        """Test clearing current hand info."""
        await service.clear_current_hand("table_a")

        mock_repo.upsert_table_status.assert_called_once()
        call_kwargs = mock_repo.upsert_table_status.call_args.kwargs
        assert call_kwargs["current_hand_id"] is None
        assert call_kwargs["current_hand_number"] is None
        assert call_kwargs["hand_start_time"] is None


class TestMonitoringServiceHandEvents:
    """Tests for hand processing events."""

    async def test_on_hand_started(self, service, mock_repo):
        """Test hand start event."""
        await service.on_hand_started("table_a", hand_number=42)

        mock_repo.upsert_table_status.assert_called_once()
        call_kwargs = mock_repo.upsert_table_status.call_args.kwargs
        assert call_kwargs["table_id"] == "table_a"
        assert call_kwargs["current_hand_number"] == 42
        assert call_kwargs["hand_start_time"] is not None

    async def test_on_hand_processed_triggers_a_grade_alert(self, service, mock_repo):
        """Test that A-grade hand triggers alert."""
        alerts_received = []
        service.set_alert_callback(lambda a: alerts_received.append(a))

        # Create mock result and grade
        mock_result = MagicMock()
        mock_result.table_id = "table_a"
        mock_result.hand_number = 42
        mock_result.rank_name = "Royal Flush"
        mock_result.is_premium = True
        mock_result.cross_validated = True
        mock_result.requires_review = False

        mock_grade = MagicMock()
        mock_grade.grade = "A"

        await service.on_hand_processed(mock_result, mock_grade, hand_id=123)

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == AlertType.A_GRADE_HAND
        assert "table_a" in alerts_received[0].message

    async def test_on_hand_processed_no_alert_for_b_grade(self, service, mock_repo):
        """Test that B-grade hand does not trigger alert."""
        alerts_received = []
        service.set_alert_callback(lambda a: alerts_received.append(a))

        mock_result = MagicMock()
        mock_result.table_id = "table_a"
        mock_result.hand_number = 42
        mock_result.rank_name = "Full House"
        mock_result.cross_validated = True
        mock_result.requires_review = False

        mock_grade = MagicMock()
        mock_grade.grade = "B"

        await service.on_hand_processed(mock_result, mock_grade)

        assert len(alerts_received) == 0


class TestMonitoringServiceRecordingEvents:
    """Tests for recording session events."""

    async def test_on_recording_started(self, service, mock_repo):
        """Test recording start event."""
        await service.on_recording_started(
            table_id="table_a",
            session_id="session_001",
            vmix_input=1,
        )

        mock_repo.create_recording_session.assert_called_once()
        call_kwargs = mock_repo.create_recording_session.call_args.kwargs
        assert call_kwargs["table_id"] == "table_a"
        assert call_kwargs["session_id"] == "session_001"
        assert call_kwargs["vmix_input"] == 1

    async def test_on_recording_stopped(self, service, mock_repo):
        """Test recording stop event."""
        await service.on_recording_stopped(
            session_id="session_001",
            status="completed",
            file_size_mb=1024.5,
            file_path="/recordings/session_001.mp4",
        )

        mock_repo.update_recording_session.assert_called_once()
        call_kwargs = mock_repo.update_recording_session.call_args.kwargs
        assert call_kwargs["session_id"] == "session_001"
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["file_size_mb"] == 1024.5

    async def test_recording_error_triggers_alert(self, service, mock_repo):
        """Test that recording error triggers alert."""
        alerts_received = []
        service.set_alert_callback(lambda a: alerts_received.append(a))

        await service.on_recording_stopped(
            session_id="session_001",
            status="error",
        )

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == AlertType.RECORDING_ERROR


class TestMonitoringServiceHealth:
    """Tests for system health logging."""

    async def test_log_service_health(self, service, mock_repo):
        """Test logging service health."""
        await service.log_service_health(
            service_name="PostgreSQL",
            status="connected",
            latency_ms=12,
            message="OK",
        )

        mock_repo.log_health.assert_called_once()
        call_kwargs = mock_repo.log_health.call_args.kwargs
        assert call_kwargs["service_name"] == "PostgreSQL"
        assert call_kwargs["status"] == "connected"
        assert call_kwargs["latency_ms"] == 12

    async def test_health_error_triggers_alert(self, service, mock_repo):
        """Test that health error triggers alert."""
        alerts_received = []
        service.set_alert_callback(lambda a: alerts_received.append(a))

        await service.log_service_health(
            service_name="Gemini API",
            status="error",
            message="Rate limit exceeded",
        )

        assert len(alerts_received) == 1
        assert alerts_received[0].alert_type == AlertType.SYSTEM_ERROR


class TestMonitoringServiceLifecycle:
    """Tests for service lifecycle."""

    async def test_start_stop(self, service):
        """Test starting and stopping service."""
        await service.start()
        assert service._running is True
        assert service._health_check_task is not None

        await service.stop()
        assert service._running is False

    async def test_set_alert_callback(self, service):
        """Test setting alert callback."""
        callback = MagicMock()
        service.set_alert_callback(callback)
        assert service._on_alert == callback

        service.set_alert_callback(None)
        assert service._on_alert is None
