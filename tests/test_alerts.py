"""Tests for Alert system (PRD-0008 Phase 2.3)."""

from datetime import UTC, datetime

import pytest

from src.dashboard.alerts import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertType,
)


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self) -> None:
        """Test basic alert creation."""
        alert = Alert(
            alert_type=AlertType.CONNECTION_LOST,
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="Test message",
            table_id="table_1",
        )

        assert alert.alert_type == AlertType.CONNECTION_LOST
        assert alert.severity == AlertSeverity.ERROR
        assert alert.title == "Test Alert"
        assert alert.message == "Test message"
        assert alert.table_id == "table_1"
        assert alert.acknowledged is False
        assert alert.id != ""  # Auto-generated

    def test_alert_id_generation(self) -> None:
        """Test alert ID auto-generation."""
        alert1 = Alert(
            alert_type=AlertType.CONNECTION_LOST,
            severity=AlertSeverity.ERROR,
            title="Alert 1",
            message="Message 1",
        )
        alert2 = Alert(
            alert_type=AlertType.CONNECTION_LOST,
            severity=AlertSeverity.ERROR,
            title="Alert 2",
            message="Message 2",
        )

        assert alert1.id != alert2.id
        assert alert1.id.startswith("connection_lost_")

    def test_alert_to_dict(self) -> None:
        """Test alert serialization."""
        alert = Alert(
            alert_type=AlertType.GRADE_A_HAND,
            severity=AlertSeverity.INFO,
            title="Grade A",
            message="Great hand!",
            table_id="table_1",
            metadata={"hand_number": 123},
        )

        data = alert.to_dict()

        assert data["type"] == "grade_a_hand"
        assert data["severity"] == "info"
        assert data["title"] == "Grade A"
        assert data["message"] == "Great hand!"
        assert data["table_id"] == "table_1"
        assert data["metadata"]["hand_number"] == 123
        assert data["acknowledged"] is False
        assert "timestamp" in data


class TestAlertManager:
    """Tests for AlertManager."""

    def test_alert_manager_creation(self) -> None:
        """Test AlertManager creation."""
        manager = AlertManager()

        assert manager.get_alerts() == []
        assert manager.get_alert_counts()["total"] == 0

    def test_connection_lost_alert(self) -> None:
        """Test connection lost alert creation."""
        manager = AlertManager()
        # First set connection as connected
        manager._connection_states["table_1"] = {"primary_connected": True}

        alert = manager.alert_connection_lost("table_1", "primary")

        assert alert.alert_type == AlertType.CONNECTION_LOST
        assert alert.severity == AlertSeverity.ERROR
        assert "PokerGFX RFID" in alert.title
        assert alert.table_id == "table_1"
        assert len(manager.get_alerts()) == 1

    def test_connection_lost_duplicate_prevention(self) -> None:
        """Test that duplicate connection lost alerts are prevented."""
        manager = AlertManager()
        # Set as already disconnected
        manager._connection_states["table_1"] = {"primary_connected": False}

        alert = manager.alert_connection_lost("table_1", "primary")

        # Should not create new alert
        assert "duplicate" in alert.title.lower()

    def test_connection_restored_alert(self) -> None:
        """Test connection restored alert creation."""
        manager = AlertManager()
        # Set as disconnected first
        manager._connection_states["table_1"] = {"primary_connected": False}

        alert = manager.alert_connection_restored("table_1", "primary")

        assert alert.alert_type == AlertType.CONNECTION_RESTORED
        assert alert.severity == AlertSeverity.INFO
        assert "Restored" in alert.title

    def test_grade_a_hand_alert(self) -> None:
        """Test Grade A hand alert creation."""
        manager = AlertManager()

        alert = manager.alert_grade_a_hand(
            table_id="table_1",
            hand_number=42,
            hand_rank="Full House",
            conditions_met=["premium_hand", "long_playtime"],
        )

        assert alert.alert_type == AlertType.GRADE_A_HAND
        assert alert.severity == AlertSeverity.INFO
        assert "Grade A" in alert.title
        assert alert.metadata["hand_number"] == 42
        assert alert.metadata["hand_rank"] == "Full House"
        assert "premium_hand" in alert.metadata["conditions_met"]

    def test_system_error_alert(self) -> None:
        """Test system error alert creation."""
        manager = AlertManager()

        alert = manager.alert_system_error(
            service_name="vMix",
            error_message="Connection timeout",
            table_id="table_1",
        )

        assert alert.alert_type == AlertType.SYSTEM_ERROR
        assert alert.severity == AlertSeverity.ERROR
        assert "vMix" in alert.title

    def test_health_warning_alert(self) -> None:
        """Test health warning alert creation."""
        manager = AlertManager()

        alert = manager.alert_health_warning(
            service_name="Database",
            warning_message="High latency detected",
            latency_ms=500,
        )

        assert alert.alert_type == AlertType.HEALTH_WARNING
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metadata["latency_ms"] == 500

    def test_acknowledge_alert(self) -> None:
        """Test alert acknowledgment."""
        manager = AlertManager()
        alert = manager.alert_system_error("Test", "Error")

        assert manager.acknowledge_alert(alert.id) is True
        assert alert.acknowledged is True

    def test_acknowledge_nonexistent_alert(self) -> None:
        """Test acknowledging nonexistent alert."""
        manager = AlertManager()

        assert manager.acknowledge_alert("nonexistent") is False

    def test_get_alerts_filtering(self) -> None:
        """Test alert filtering."""
        manager = AlertManager()

        # Create various alerts
        manager._connection_states["table_1"] = {"primary_connected": True}
        manager.alert_connection_lost("table_1", "primary")
        manager.alert_grade_a_hand("table_1", 1, "Full House", [])
        manager.alert_system_error("Test", "Error")

        # Filter by type
        connection_alerts = manager.get_alerts(alert_type=AlertType.CONNECTION_LOST)
        assert len(connection_alerts) == 1

        # Filter by severity
        error_alerts = manager.get_alerts(severity=AlertSeverity.ERROR)
        assert len(error_alerts) == 2  # connection_lost and system_error

    def test_get_active_alerts(self) -> None:
        """Test getting unacknowledged alerts."""
        manager = AlertManager()

        alert1 = manager.alert_system_error("Test1", "Error1")
        manager.alert_system_error("Test2", "Error2")

        manager.acknowledge_alert(alert1.id)

        active = manager.get_active_alerts()
        assert len(active) == 1
        assert active[0].title == "Test2 Error"

    def test_get_alert_counts(self) -> None:
        """Test alert count statistics."""
        manager = AlertManager()
        manager._connection_states["table_1"] = {"primary_connected": True}

        manager.alert_connection_lost("table_1", "primary")
        manager.alert_grade_a_hand("table_1", 1, "Full House", [])
        alert = manager.alert_system_error("Test", "Error")
        manager.acknowledge_alert(alert.id)

        counts = manager.get_alert_counts()

        assert counts["total"] == 3
        assert counts["unacknowledged"] == 2
        assert counts["connection_lost"] == 1
        assert counts["grade_a_hand"] == 1
        assert counts["system_error"] == 1

    def test_clear_acknowledged(self) -> None:
        """Test clearing acknowledged alerts."""
        manager = AlertManager()

        alert1 = manager.alert_system_error("Test1", "Error1")
        manager.alert_system_error("Test2", "Error2")

        manager.acknowledge_alert(alert1.id)
        cleared = manager.clear_acknowledged()

        assert cleared == 1
        assert len(manager.get_alerts()) == 1

    def test_max_history_limit(self) -> None:
        """Test alert history limit."""
        manager = AlertManager(max_history=5)

        for i in range(10):
            manager.alert_system_error(f"Test{i}", f"Error{i}")

        assert len(manager.get_alerts()) == 5

    def test_on_alert_callback(self) -> None:
        """Test alert callback invocation."""
        called_alerts: list[Alert] = []

        def on_alert(alert: Alert) -> None:
            called_alerts.append(alert)

        manager = AlertManager(on_alert=on_alert)
        manager.alert_system_error("Test", "Error")

        assert len(called_alerts) == 1
        assert called_alerts[0].title == "Test Error"

    def test_secondary_connection_alerts(self) -> None:
        """Test secondary (Gemini) connection alerts."""
        manager = AlertManager()
        manager._connection_states["table_1"] = {"secondary_connected": True}

        alert = manager.alert_connection_lost("table_1", "secondary")

        assert "Gemini AI Video" in alert.title
        assert alert.metadata["source"] == "secondary"


class TestAlertIntegrationWithMonitoringService:
    """Integration tests for alerts with MonitoringService."""

    @pytest.fixture
    def mock_db_manager(self) -> object:
        """Create a mock DatabaseManager."""
        from unittest.mock import MagicMock
        return MagicMock()

    @pytest.fixture
    def mock_repo(self) -> object:
        """Create a mock MonitoringRepository."""
        from unittest.mock import AsyncMock, MagicMock
        repo = MagicMock()
        repo.upsert_table_status = AsyncMock()
        repo.get_all_table_statuses = AsyncMock(return_value=[])
        repo.get_grade_distribution = AsyncMock(return_value={})
        repo.get_active_recording_sessions = AsyncMock(return_value=[])
        repo.get_all_latest_health = AsyncMock(return_value={})
        repo.get_today_stats = AsyncMock(return_value={})
        return repo

    async def test_connection_change_generates_alert(
        self, mock_db_manager: object, mock_repo: object
    ) -> None:
        """Test that connection status changes generate alerts."""
        from src.dashboard.monitoring_service import MonitoringService

        service = MonitoringService(mock_db_manager, mock_repo)  # type: ignore[arg-type]
        await service.initialize()

        # Set initial connected state
        service._table_statuses["table_1"] = {"primary_connected": True}

        # Disconnect should generate alert
        await service.update_table_connection("table_1", primary_connected=False)

        alerts = service.alert_manager.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].alert_type == AlertType.CONNECTION_LOST

    async def test_dashboard_state_includes_alerts(
        self, mock_db_manager: object, mock_repo: object
    ) -> None:
        """Test that dashboard state includes alert information."""
        from src.dashboard.monitoring_service import MonitoringService

        service = MonitoringService(mock_db_manager, mock_repo)  # type: ignore[arg-type]
        await service.initialize()

        # Generate an alert
        service.alert_manager.alert_system_error("Test", "Error")

        state = await service.get_dashboard_state()

        assert "alerts" in state
        alerts_data = state["alerts"]
        assert isinstance(alerts_data, dict)
        assert "active" in alerts_data
        assert "counts" in alerts_data
        assert len(alerts_data["active"]) == 1  # type: ignore[arg-type]
