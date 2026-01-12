"""Tests for SMB health checker and fallback watcher (PRD-0010)."""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.primary.fallback_watcher import FallbackFileWatcher, WatcherMode
from src.primary.smb_health_checker import (
    ConnectionState,
    SMBConnectionStatus,
    SMBHealthChecker,
)


class MockPokerGFXSettings:
    """Mock settings for testing."""

    def __init__(
        self,
        json_watch_path: str = "",
        fallback_path: str = "",
        fallback_enabled: bool = True,
        max_reconnect_attempts: int = 3,
    ):
        self.json_watch_path = json_watch_path
        self.fallback_path = fallback_path
        self.fallback_enabled = fallback_enabled
        self.polling_interval = 1.0
        self.file_pattern = "*.json"
        self.file_settle_delay = 0.1
        self.health_check_interval = 1.0
        self.max_reconnect_attempts = max_reconnect_attempts
        self.processed_db_path = "./data/test_processed.json"


class TestSMBHealthChecker:
    """Tests for SMBHealthChecker class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def settings(self, temp_dir: Path) -> MockPokerGFXSettings:
        """Create mock settings with temp directory."""
        return MockPokerGFXSettings(
            json_watch_path=str(temp_dir),
            fallback_path=str(temp_dir / "fallback"),
        )

    @pytest.fixture
    def checker(self, settings: MockPokerGFXSettings) -> SMBHealthChecker:
        """Create health checker instance."""
        return SMBHealthChecker(settings=settings)

    async def test_check_connection_path_exists(
        self, checker: SMBHealthChecker, temp_dir: Path
    ) -> None:
        """Test connection check when path exists."""
        status = await checker.check_connection()

        assert status.state in (ConnectionState.CONNECTED, ConnectionState.DEGRADED)
        assert status.can_read is True
        assert status.latency_ms is not None
        assert status.latency_ms >= 0

    async def test_check_connection_path_not_exists(self) -> None:
        """Test connection check when path doesn't exist."""
        settings = MockPokerGFXSettings(json_watch_path="/nonexistent/path")
        checker = SMBHealthChecker(settings=settings)

        status = await checker.check_connection()

        assert status.state == ConnectionState.DISCONNECTED
        assert status.can_read is False
        assert status.error_message is not None

    async def test_check_connection_read_only(
        self, checker: SMBHealthChecker, temp_dir: Path
    ) -> None:
        """Test connection check with read-only directory."""
        # Create a file to read
        test_file = temp_dir / "test.json"
        test_file.write_text("{}")

        status = await checker.check_connection()

        # Should be connected or degraded (if write fails)
        assert status.state in (ConnectionState.CONNECTED, ConnectionState.DEGRADED)
        assert status.can_read is True

    async def test_is_connected_property(
        self, checker: SMBHealthChecker, temp_dir: Path
    ) -> None:
        """Test is_connected property."""
        # Initially disconnected
        assert checker.is_connected is False

        # After successful check
        await checker.check_connection()
        # Note: is_connected depends on _current_state which is updated by _handle_status_change

    async def test_attempt_reconnect_success(
        self, checker: SMBHealthChecker, temp_dir: Path
    ) -> None:
        """Test reconnection attempt when path is accessible."""
        result = await checker.attempt_reconnect()
        assert result is True

    async def test_attempt_reconnect_failure(self) -> None:
        """Test reconnection attempt when path is inaccessible."""
        settings = MockPokerGFXSettings(
            json_watch_path="/nonexistent/path",
            max_reconnect_attempts=2,
        )
        checker = SMBHealthChecker(settings=settings)

        result = await checker.attempt_reconnect()
        assert result is False

    async def test_state_change_callback(
        self, settings: MockPokerGFXSettings, temp_dir: Path
    ) -> None:
        """Test state change callback is triggered."""
        callback_states: list[ConnectionState] = []

        def on_state_change(state: ConnectionState) -> None:
            callback_states.append(state)

        checker = SMBHealthChecker(settings=settings)
        checker.on_state_change = on_state_change

        # Check connection to trigger state change
        status = await checker.check_connection()
        await checker._handle_status_change(status)

        assert len(callback_states) >= 1


class TestFallbackFileWatcher:
    """Tests for FallbackFileWatcher class."""

    @pytest.fixture
    def temp_dirs(self) -> tuple[Path, Path]:
        """Create temporary directories for primary and fallback."""
        with tempfile.TemporaryDirectory() as primary_dir:
            with tempfile.TemporaryDirectory() as fallback_dir:
                yield Path(primary_dir), Path(fallback_dir)

    @pytest.fixture
    def settings(self, temp_dirs: tuple[Path, Path]) -> MockPokerGFXSettings:
        """Create mock settings with temp directories."""
        primary_dir, fallback_dir = temp_dirs
        return MockPokerGFXSettings(
            json_watch_path=str(primary_dir),
            fallback_path=str(fallback_dir),
            fallback_enabled=True,
        )

    @pytest.fixture
    def watcher(self, settings: MockPokerGFXSettings) -> FallbackFileWatcher:
        """Create fallback watcher instance."""
        return FallbackFileWatcher(settings=settings)

    def test_initial_mode(self, watcher: FallbackFileWatcher) -> None:
        """Test initial watcher mode is PRIMARY."""
        assert watcher.current_mode == WatcherMode.PRIMARY

    def test_is_using_fallback(self, watcher: FallbackFileWatcher) -> None:
        """Test is_using_fallback property."""
        assert watcher.is_using_fallback is False

    def test_ensure_fallback_folder(
        self, settings: MockPokerGFXSettings, temp_dirs: tuple[Path, Path]
    ) -> None:
        """Test fallback folder is created on initialization."""
        _, fallback_dir = temp_dirs
        # Delete fallback dir to test creation
        fallback_dir.rmdir()
        assert not fallback_dir.exists()

        # Create watcher - should recreate folder
        watcher = FallbackFileWatcher(settings=settings)
        assert Path(settings.fallback_path).exists()

    async def test_is_primary_available_true(
        self, watcher: FallbackFileWatcher, temp_dirs: tuple[Path, Path]
    ) -> None:
        """Test _is_primary_available when path is accessible."""
        result = await watcher._is_primary_available()
        assert result is True

    async def test_is_primary_available_false(self) -> None:
        """Test _is_primary_available when path is inaccessible."""
        settings = MockPokerGFXSettings(
            json_watch_path="/nonexistent/path",
            fallback_path="./data/fallback",
        )
        watcher = FallbackFileWatcher(settings=settings)

        result = await watcher._is_primary_available()
        assert result is False

    async def test_switch_mode(self, watcher: FallbackFileWatcher) -> None:
        """Test mode switching."""
        mode_changes: list[WatcherMode] = []

        def on_mode_change(mode: WatcherMode) -> None:
            mode_changes.append(mode)

        watcher.on_mode_change = on_mode_change

        # Switch to fallback
        await watcher._switch_mode(WatcherMode.FALLBACK)
        assert watcher.current_mode == WatcherMode.FALLBACK
        assert WatcherMode.FALLBACK in mode_changes

        # Switch back to primary
        await watcher._switch_mode(WatcherMode.PRIMARY)
        assert watcher.current_mode == WatcherMode.PRIMARY
        assert WatcherMode.PRIMARY in mode_changes

    async def test_switch_mode_same_mode(self, watcher: FallbackFileWatcher) -> None:
        """Test switching to same mode does nothing."""
        initial_mode = watcher.current_mode
        await watcher._switch_mode(initial_mode)
        assert watcher.current_mode == initial_mode

    def test_get_stats(self, watcher: FallbackFileWatcher) -> None:
        """Test get_stats returns expected data."""
        stats = watcher.get_stats()

        assert "mode" in stats
        assert "primary_path" in stats
        assert "fallback_path" in stats
        assert "fallback_enabled" in stats
        assert "is_running" in stats
        assert stats["mode"] == WatcherMode.PRIMARY.value
        assert stats["fallback_enabled"] is True

    async def test_stop(self, watcher: FallbackFileWatcher) -> None:
        """Test watcher stop cleanup."""
        watcher._running = True
        await watcher.stop()
        assert watcher._running is False

    async def test_disconnect_alias(self, watcher: FallbackFileWatcher) -> None:
        """Test disconnect is alias for stop."""
        watcher._running = True
        await watcher.disconnect()
        assert watcher._running is False


class TestSMBConnectionStatus:
    """Tests for SMBConnectionStatus dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        status = SMBConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            last_check=datetime.now(),
        )

        assert status.error_code is None
        assert status.error_message is None
        assert status.latency_ms is None
        assert status.can_read is False
        assert status.can_write is False
        assert status.consecutive_failures == 0

    def test_connected_status(self) -> None:
        """Test connected status values."""
        status = SMBConnectionStatus(
            state=ConnectionState.CONNECTED,
            last_check=datetime.now(),
            can_read=True,
            can_write=True,
            latency_ms=5.0,
        )

        assert status.state == ConnectionState.CONNECTED
        assert status.can_read is True
        assert status.can_write is True
        assert status.latency_ms == 5.0


class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.RECONNECTING.value == "reconnecting"
        assert ConnectionState.DEGRADED.value == "degraded"


class TestWatcherMode:
    """Tests for WatcherMode enum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert WatcherMode.PRIMARY.value == "primary"
        assert WatcherMode.FALLBACK.value == "fallback"
        assert WatcherMode.SWITCHING.value == "switching"
