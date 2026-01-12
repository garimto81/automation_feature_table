"""Fallback file watcher for SMB connection failures.

PRD-0010: NAS SMB 연동 - SMB 실패 시 로컬 폴더로 자동 전환
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.models.hand import HandResult
from src.primary.json_file_watcher import JSONFileWatcher
from src.primary.smb_health_checker import ConnectionState, SMBHealthChecker

if TYPE_CHECKING:
    from src.config.settings import PokerGFXSettings

logger = logging.getLogger(__name__)


class WatcherMode(str, Enum):
    """Active watcher mode."""

    PRIMARY = "primary"  # NAS SMB
    FALLBACK = "fallback"  # Local folder
    SWITCHING = "switching"  # Transitioning between modes


class FallbackFileWatcher:
    """File watcher with automatic fallback to local folder.

    When SMB connection fails repeatedly, automatically switches
    to monitoring a local fallback folder for manual file imports.

    Usage:
        watcher = FallbackFileWatcher(settings)
        async for result in watcher.listen():
            process(result)
    """

    def __init__(
        self,
        settings: PokerGFXSettings,
        on_mode_change: Callable[[WatcherMode], None] | None = None,
    ):
        """Initialize fallback watcher.

        Args:
            settings: PokerGFX settings
            on_mode_change: Callback when watcher mode changes
        """
        self.settings = settings
        self.on_mode_change = on_mode_change

        self._mode = WatcherMode.PRIMARY
        self._running = False
        self._primary_watcher: JSONFileWatcher | None = None
        self._fallback_watcher: JSONFileWatcher | None = None
        self._health_checker: SMBHealthChecker | None = None

        # Ensure fallback folder exists
        self._ensure_fallback_folder()

    def _ensure_fallback_folder(self) -> None:
        """Create fallback folder if it doesn't exist."""
        fallback_path = Path(self.settings.fallback_path)
        fallback_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Fallback folder ready: {fallback_path}")

    @property
    def current_mode(self) -> WatcherMode:
        """Get current watcher mode."""
        return self._mode

    @property
    def is_using_fallback(self) -> bool:
        """Check if currently using fallback mode."""
        return self._mode == WatcherMode.FALLBACK

    async def _is_primary_available(self) -> bool:
        """Check if primary (SMB) path is accessible."""
        primary_path = Path(self.settings.json_watch_path)

        if not primary_path.exists():
            return False

        try:
            list(primary_path.iterdir())
            return True
        except (OSError, PermissionError):
            return False

    def _create_primary_watcher(self) -> JSONFileWatcher:
        """Create watcher for primary SMB path."""
        return JSONFileWatcher(self.settings)

    def _create_fallback_watcher(self) -> JSONFileWatcher:
        """Create watcher for fallback local path."""
        # Create a modified settings for fallback path
        from dataclasses import dataclass

        @dataclass
        class FallbackSettings:
            """Temporary settings for fallback watcher."""

            json_watch_path: str
            polling_interval: float
            processed_db_path: str
            file_pattern: str
            file_settle_delay: float
            max_reconnect_attempts: int

        fallback_settings = FallbackSettings(
            json_watch_path=self.settings.fallback_path,
            polling_interval=self.settings.polling_interval,
            processed_db_path="./data/processed_fallback_files.json",
            file_pattern=self.settings.file_pattern,
            file_settle_delay=self.settings.file_settle_delay,
            max_reconnect_attempts=self.settings.max_reconnect_attempts,
        )

        return JSONFileWatcher(fallback_settings)  # type: ignore[arg-type]

    async def _switch_mode(self, new_mode: WatcherMode) -> None:
        """Switch between primary and fallback modes."""
        if new_mode == self._mode:
            return

        old_mode = self._mode
        self._mode = WatcherMode.SWITCHING

        logger.info(f"Switching watcher mode: {old_mode.value} → {new_mode.value}")

        # Stop current watcher
        if old_mode == WatcherMode.PRIMARY and self._primary_watcher:
            await self._primary_watcher.stop()
            self._primary_watcher = None
        elif old_mode == WatcherMode.FALLBACK and self._fallback_watcher:
            await self._fallback_watcher.stop()
            self._fallback_watcher = None

        self._mode = new_mode

        if self.on_mode_change:
            self.on_mode_change(new_mode)

    async def _handle_smb_state_change(self, state: ConnectionState) -> None:
        """Handle SMB connection state changes."""
        if state in (ConnectionState.CONNECTED, ConnectionState.DEGRADED):
            if self._mode == WatcherMode.FALLBACK:
                logger.info("SMB connection restored, switching back to primary")
                await self._switch_mode(WatcherMode.PRIMARY)
        elif state == ConnectionState.DISCONNECTED:
            if self._mode == WatcherMode.PRIMARY:
                logger.warning("SMB connection lost, switching to fallback")
                await self._switch_mode(WatcherMode.FALLBACK)

    async def listen(self) -> AsyncIterator[HandResult]:
        """Listen for files with automatic fallback.

        Monitors primary SMB path, automatically switches to
        fallback local folder if connection fails.

        Yields:
            HandResult objects from either primary or fallback source
        """
        self._running = True

        # Initialize health checker if fallback is enabled
        if self.settings.fallback_enabled:
            self._health_checker = SMBHealthChecker(self.settings)

            def _state_change_handler(s: ConnectionState) -> None:
                asyncio.create_task(self._handle_smb_state_change(s))

            self._health_checker.on_state_change = _state_change_handler

        # Determine initial mode
        if await self._is_primary_available():
            self._mode = WatcherMode.PRIMARY
            logger.info("Starting in PRIMARY mode (SMB)")
        else:
            if self.settings.fallback_enabled:
                self._mode = WatcherMode.FALLBACK
                logger.warning("SMB unavailable, starting in FALLBACK mode")
            else:
                raise RuntimeError(
                    f"Cannot access primary path: {self.settings.json_watch_path} "
                    f"and fallback is disabled"
                )

        if self.on_mode_change:
            self.on_mode_change(self._mode)

        try:
            while self._running:
                try:
                    if self._mode == WatcherMode.PRIMARY:
                        # Use primary SMB watcher
                        if not self._primary_watcher:
                            self._primary_watcher = self._create_primary_watcher()

                        async for result in self._primary_watcher.listen():
                            if not self._running or self._mode != WatcherMode.PRIMARY:
                                break
                            yield result

                    elif self._mode == WatcherMode.FALLBACK:
                        # Use fallback local watcher
                        if not self._fallback_watcher:
                            self._fallback_watcher = self._create_fallback_watcher()

                        async for result in self._fallback_watcher.listen():
                            if not self._running or self._mode != WatcherMode.FALLBACK:
                                break
                            yield result

                    elif self._mode == WatcherMode.SWITCHING:
                        # Wait during mode transition
                        await asyncio.sleep(0.5)

                except RuntimeError as e:
                    # Primary watcher failed to start
                    if self._mode == WatcherMode.PRIMARY:
                        logger.error(f"Primary watcher error: {e}")
                        if self.settings.fallback_enabled:
                            await self._switch_mode(WatcherMode.FALLBACK)
                        else:
                            raise
                    else:
                        raise

                except Exception as e:
                    logger.error(f"Watcher error: {e}")
                    await asyncio.sleep(5.0)

        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop all watchers and cleanup."""
        self._running = False

        if self._primary_watcher:
            await self._primary_watcher.stop()
            self._primary_watcher = None

        if self._fallback_watcher:
            await self._fallback_watcher.stop()
            self._fallback_watcher = None

        if self._health_checker:
            await self._health_checker.stop_monitoring()
            self._health_checker = None

        logger.info("Fallback watcher stopped")

    async def disconnect(self) -> None:
        """Alias for stop() - compatibility with PokerGFXClient interface."""
        await self.stop()

    def get_stats(self) -> dict[str, object]:
        """Get watcher statistics.

        Returns:
            Dictionary with statistics
        """
        active_watcher = (
            self._primary_watcher
            if self._mode == WatcherMode.PRIMARY
            else self._fallback_watcher
        )

        return {
            "mode": self._mode.value,
            "primary_path": self.settings.json_watch_path,
            "fallback_path": self.settings.fallback_path,
            "fallback_enabled": self.settings.fallback_enabled,
            "is_running": self._running,
            "active_watcher_stats": (
                active_watcher.get_stats() if active_watcher else None
            ),
        }
