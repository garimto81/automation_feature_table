"""SMB connection health checker for NAS file watching.

PRD-0010: NAS SMB 연동 - 연결 상태 모니터링 및 자동 복구
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import PokerGFXSettings

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """SMB connection states."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"  # Read-only (write test failed)


@dataclass
class SMBConnectionStatus:
    """SMB connection status details."""

    state: ConnectionState
    last_check: datetime
    error_code: int | None = None
    error_message: str | None = None
    latency_ms: float | None = None
    can_read: bool = False
    can_write: bool = False
    consecutive_failures: int = 0


@dataclass
class SMBHealthChecker:
    """SMB connection health monitor with auto-reconnect.

    Provides:
    - 3-stage connection verification (path → read → write)
    - Periodic health checks
    - Exponential backoff reconnection
    - Connection state callbacks

    Usage:
        checker = SMBHealthChecker(settings)
        checker.on_connected = lambda: print("Connected!")
        checker.on_disconnected = lambda status: print(f"Lost: {status}")
        await checker.start_monitoring()
    """

    settings: PokerGFXSettings
    on_connected: Callable[[], None] | None = None
    on_disconnected: Callable[[SMBConnectionStatus], None] | None = None
    on_state_change: Callable[[ConnectionState], None] | None = None

    _running: bool = field(default=False, init=False)
    _current_state: ConnectionState = field(
        default=ConnectionState.DISCONNECTED, init=False
    )
    _status: SMBConnectionStatus = field(init=False)
    _reconnect_task: asyncio.Task[None] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize status after dataclass creation."""
        self._status = SMBConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            last_check=datetime.now(),
        )

    @property
    def is_connected(self) -> bool:
        """Check if currently connected (including degraded)."""
        return self._current_state in (
            ConnectionState.CONNECTED,
            ConnectionState.DEGRADED,
        )

    @property
    def current_status(self) -> SMBConnectionStatus:
        """Get current connection status."""
        return self._status

    async def check_connection(self) -> SMBConnectionStatus:
        """Perform 3-stage SMB connection verification.

        Stage 1: Path existence check
        Stage 2: Directory read test (list files)
        Stage 3: Write test (touch and delete temp file)

        Returns:
            SMBConnectionStatus with verification results
        """
        start_time = datetime.now()
        watch_path = Path(self.settings.json_watch_path)

        status = SMBConnectionStatus(
            state=ConnectionState.DISCONNECTED,
            last_check=start_time,
        )

        # Stage 1: Path existence
        try:
            if not watch_path.exists():
                status.error_message = f"Path does not exist: {watch_path}"
                status.error_code = 2  # ERROR_FILE_NOT_FOUND
                logger.debug(f"Stage 1 failed: {status.error_message}")
                return status
        except OSError as e:
            status.error_message = f"Path access error: {e}"
            status.error_code = e.errno
            logger.debug(f"Stage 1 OSError: {e}")
            return status

        # Stage 2: Directory read test
        try:
            files = list(watch_path.iterdir())
            status.can_read = True
            logger.debug(f"Stage 2 passed: Found {len(files)} items")
        except PermissionError as e:
            status.error_message = f"Read permission denied: {e}"
            status.error_code = 5  # ERROR_ACCESS_DENIED
            logger.debug(f"Stage 2 PermissionError: {e}")
            return status
        except OSError as e:
            status.error_message = f"Directory read error: {e}"
            status.error_code = e.errno
            logger.debug(f"Stage 2 OSError: {e}")
            return status

        # Stage 3: Write test (optional, may fail for read-only mounts)
        test_file = watch_path / ".smb_health_check"
        try:
            test_file.touch()
            test_file.unlink()
            status.can_write = True
            status.state = ConnectionState.CONNECTED
            logger.debug("Stage 3 passed: Write test successful")
        except PermissionError:
            # Read-only mount is acceptable
            status.state = ConnectionState.DEGRADED
            status.error_message = "Read-only: write test failed"
            logger.debug("Stage 3 degraded: Write permission denied (read-only OK)")
        except OSError as e:
            # Write failed but read works = degraded
            status.state = ConnectionState.DEGRADED
            status.error_message = f"Write test failed: {e}"
            logger.debug(f"Stage 3 degraded: {e}")

        # Calculate latency
        end_time = datetime.now()
        status.latency_ms = (end_time - start_time).total_seconds() * 1000

        return status

    async def start_monitoring(self) -> None:
        """Start periodic health check loop.

        Runs health checks at configured interval and triggers
        callbacks on state changes.
        """
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True
        interval = self.settings.health_check_interval
        logger.info(f"Starting SMB health monitoring (interval: {interval}s)")

        while self._running:
            try:
                status = await self.check_connection()
                await self._handle_status_change(status)
                self._status = status

                if status.state in (
                    ConnectionState.CONNECTED,
                    ConnectionState.DEGRADED,
                ):
                    status.consecutive_failures = 0
                else:
                    status.consecutive_failures = self._status.consecutive_failures + 1

            except Exception as e:
                logger.error(f"Health check error: {e}")
                self._status.consecutive_failures += 1

            await asyncio.sleep(interval)

    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        self._running = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        logger.info("SMB health monitoring stopped")

    async def attempt_reconnect(self) -> bool:
        """Attempt SMB reconnection with exponential backoff.

        Tries up to max_reconnect_attempts times with delays:
        5s → 10s → 20s → 40s → 60s (max)

        Returns:
            True if reconnection successful, False otherwise
        """
        max_attempts = self.settings.max_reconnect_attempts
        base_delay = 5.0
        max_delay = 60.0

        self._current_state = ConnectionState.RECONNECTING
        if self.on_state_change:
            self.on_state_change(self._current_state)

        for attempt in range(1, max_attempts + 1):
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.info(
                f"Reconnection attempt {attempt}/{max_attempts} "
                f"(delay: {delay}s)"
            )

            await asyncio.sleep(delay)

            status = await self.check_connection()
            if status.state in (ConnectionState.CONNECTED, ConnectionState.DEGRADED):
                logger.info(f"Reconnected after {attempt} attempts")
                await self._handle_status_change(status)
                return True

        logger.error(f"Reconnection failed after {max_attempts} attempts")
        return False

    async def _handle_status_change(self, new_status: SMBConnectionStatus) -> None:
        """Handle connection state transitions and trigger callbacks."""
        old_state = self._current_state
        new_state = new_status.state

        if old_state == new_state:
            return

        self._current_state = new_state
        logger.info(f"SMB state change: {old_state.value} → {new_state.value}")

        if self.on_state_change:
            self.on_state_change(new_state)

        # Trigger specific callbacks
        if new_state in (ConnectionState.CONNECTED, ConnectionState.DEGRADED):
            if old_state == ConnectionState.DISCONNECTED:
                if self.on_connected:
                    self.on_connected()
        elif new_state == ConnectionState.DISCONNECTED:
            if self.on_disconnected:
                self.on_disconnected(new_status)

            # Start reconnection if enabled
            if (
                self.settings.fallback_enabled
                and self._reconnect_task is None
                or (self._reconnect_task and self._reconnect_task.done())
            ):

                async def _reconnect_wrapper() -> None:
                    await self.attempt_reconnect()

                self._reconnect_task = asyncio.create_task(_reconnect_wrapper())
