"""Tests for DashboardWebSocket (PRD-0008)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.dashboard.websocket_server import (
    ConnectionManager,
    DashboardState,
    DashboardWebSocket,
)


class TestDashboardState:
    """Tests for DashboardState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = DashboardState()

        assert state.table_statuses == []
        assert state.grade_distribution == {}
        assert state.recording_sessions == []
        assert state.system_health == {}
        assert state.last_updated == ""

    def test_to_dict(self):
        """Test converting state to dictionary."""
        state = DashboardState(
            table_statuses=[{"table_id": "table_a"}],
            grade_distribution={"A": 5},
            last_updated="2026-01-07T00:00:00",
        )

        result = state.to_dict()

        assert result["table_statuses"] == [{"table_id": "table_a"}]
        assert result["grade_distribution"] == {"A": 5}
        assert result["last_updated"] == "2026-01-07T00:00:00"


class TestConnectionManager:
    """Tests for ConnectionManager."""

    async def test_connect_adds_websocket(self):
        """Test connecting a WebSocket."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        await manager.connect(mock_ws)

        assert mock_ws in manager.active_connections
        assert manager.connection_count == 1
        mock_ws.accept.assert_called_once()

    async def test_disconnect_removes_websocket(self):
        """Test disconnecting a WebSocket."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        await manager.connect(mock_ws)
        manager.disconnect(mock_ws)

        assert mock_ws not in manager.active_connections
        assert manager.connection_count == 0

    async def test_broadcast_sends_to_all(self):
        """Test broadcasting to all connections."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        message = {"type": "update", "data": "test"}
        await manager.broadcast(message)

        expected_json = json.dumps(message)
        ws1.send_text.assert_called_once_with(expected_json)
        ws2.send_text.assert_called_once_with(expected_json)

    async def test_broadcast_removes_failed_connections(self):
        """Test that failed connections are removed during broadcast."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_text.side_effect = Exception("Connection lost")

        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.broadcast({"test": True})

        assert ws1 in manager.active_connections
        assert ws2 not in manager.active_connections

    async def test_broadcast_no_connections(self):
        """Test broadcast with no connections does nothing."""
        manager = ConnectionManager()
        # Should not raise
        await manager.broadcast({"test": True})


class TestDashboardWebSocket:
    """Tests for DashboardWebSocket."""

    def test_init_defaults(self):
        """Test default initialization."""
        dashboard = DashboardWebSocket()

        assert dashboard.monitoring_repo is None
        assert dashboard.broadcast_interval == 1.0
        assert dashboard._running is False

    def test_init_with_repo(self):
        """Test initialization with repository."""
        mock_repo = MagicMock()
        dashboard = DashboardWebSocket(monitoring_repo=mock_repo, broadcast_interval=2.0)

        assert dashboard.monitoring_repo == mock_repo
        assert dashboard.broadcast_interval == 2.0

    async def test_start_broadcasting(self):
        """Test starting the broadcast loop."""
        dashboard = DashboardWebSocket()

        await dashboard.start_broadcasting()

        assert dashboard._running is True
        assert dashboard._broadcast_task is not None

        # Cleanup
        await dashboard.stop_broadcasting()

    async def test_stop_broadcasting(self):
        """Test stopping the broadcast loop."""
        dashboard = DashboardWebSocket()
        await dashboard.start_broadcasting()

        await dashboard.stop_broadcasting()

        assert dashboard._running is False
        assert dashboard._broadcast_task is None

    async def test_start_broadcasting_already_running(self):
        """Test starting when already running logs warning."""
        dashboard = DashboardWebSocket()
        await dashboard.start_broadcasting()

        # Second call should not start another task
        with patch("src.dashboard.websocket_server.logger") as mock_logger:
            await dashboard.start_broadcasting()
            mock_logger.warning.assert_called_once()

        await dashboard.stop_broadcasting()

    async def test_get_mock_state(self):
        """Test mock state generation."""
        dashboard = DashboardWebSocket()

        state = dashboard._get_mock_state()

        assert len(state.table_statuses) == 2
        assert "A" in state.grade_distribution
        assert len(state.recording_sessions) == 1
        assert "PostgreSQL" in state.system_health

    async def test_update_state_without_repo_uses_mock(self):
        """Test that update_state uses mock data without repo."""
        dashboard = DashboardWebSocket()

        await dashboard._update_state()

        assert dashboard._state.table_statuses != []

    async def test_update_state_with_repo(self):
        """Test update_state fetches from repository."""
        mock_repo = AsyncMock()
        mock_repo.get_all_table_statuses.return_value = []
        mock_repo.get_all_latest_health.return_value = {}
        mock_repo.get_active_recording_sessions.return_value = []
        mock_repo.get_today_stats.return_value = {"grade_distribution": {"A": 1}}

        dashboard = DashboardWebSocket(monitoring_repo=mock_repo)

        await dashboard._update_state()

        mock_repo.get_all_table_statuses.assert_called_once()
        mock_repo.get_all_latest_health.assert_called_once()
        mock_repo.get_active_recording_sessions.assert_called_once()
        mock_repo.get_today_stats.assert_called_once()

    async def test_handle_connection_sends_initial_state(self):
        """Test that initial state is sent on connection."""
        dashboard = DashboardWebSocket()
        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=Exception("Close"))

        # handle_connection catches exceptions internally
        await dashboard.handle_connection(mock_ws)

        # Should have called send_text with initial state
        assert mock_ws.send_text.called
        # Verify it was JSON with state data
        call_args = mock_ws.send_text.call_args[0][0]
        state_data = json.loads(call_args)
        assert "table_statuses" in state_data
        assert "grade_distribution" in state_data

    async def test_state_property(self):
        """Test state property returns current state."""
        dashboard = DashboardWebSocket()

        state = dashboard.state

        assert isinstance(state, DashboardState)


class TestBroadcastLoop:
    """Tests for the broadcast loop behavior."""

    async def test_broadcast_loop_skips_when_no_connections(self):
        """Test that broadcast loop doesn't fetch data with no connections."""
        mock_repo = AsyncMock()
        dashboard = DashboardWebSocket(
            monitoring_repo=mock_repo, broadcast_interval=0.01
        )

        await dashboard.start_broadcasting()
        await asyncio.sleep(0.05)  # Let loop run a few times
        await dashboard.stop_broadcasting()

        # Should not have fetched data
        mock_repo.get_all_table_statuses.assert_not_called()

    async def test_broadcast_loop_fetches_with_connections(self):
        """Test that broadcast loop fetches data when connections exist."""
        mock_repo = AsyncMock()
        mock_repo.get_all_table_statuses.return_value = []
        mock_repo.get_all_latest_health.return_value = {}
        mock_repo.get_active_recording_sessions.return_value = []
        mock_repo.get_today_stats.return_value = {}

        dashboard = DashboardWebSocket(
            monitoring_repo=mock_repo, broadcast_interval=0.01
        )

        # Add a mock connection
        mock_ws = AsyncMock()
        await dashboard.manager.connect(mock_ws)

        await dashboard.start_broadcasting()
        await asyncio.sleep(0.05)  # Let loop run
        await dashboard.stop_broadcasting()

        # Should have fetched data
        assert mock_repo.get_all_table_statuses.called
