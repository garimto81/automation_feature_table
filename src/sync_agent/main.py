"""GFX Sync Agent - GFX PC to Supabase direct synchronization.

This script runs as a background service to monitor GFX JSON output files
and sync them directly to Supabase, bypassing NAS SMB issues.

Usage:
    python -m src.sync_agent.main
    python -m src.sync_agent.main --config path/to/config.env
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from src.sync_agent.config import SyncAgentSettings
from src.sync_agent.file_handler import GFXFileWatcher
from src.sync_agent.local_queue import LocalQueue
from src.sync_agent.sync_service import SyncService

logger = logging.getLogger(__name__)


def load_settings(config_path: str | None = None) -> SyncAgentSettings:
    """Load settings from config file or environment.

    Settings are loaded from:
    1. Environment variables (highest priority)
    2. Specified config file (--config option)
    3. Default config.env in current directory
    """
    if config_path:
        from dotenv import load_dotenv
        load_dotenv(config_path, override=True)

    # SyncAgentSettings will load from environment variables
    # which may have been populated by dotenv above
    return SyncAgentSettings()  # type: ignore[call-arg]


def setup_logging(settings: SyncAgentSettings) -> None:
    """Configure logging based on settings."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if settings.log_path:
        log_path = Path(settings.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(str(log_path), encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format=log_format,
        handlers=handlers,
    )

    # Reduce noise from external libraries
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class SyncAgentApp:
    """Main application for GFX Sync Agent."""

    def __init__(self, settings: SyncAgentSettings) -> None:
        self.settings = settings
        self._running = False
        self._watcher: GFXFileWatcher | None = None
        self._sync_service: SyncService | None = None
        self._queue: LocalQueue | None = None

    async def start(self) -> None:
        """Start the sync agent."""
        logger.info("Starting GFX Sync Agent...")
        logger.info(f"Watch path: {self.settings.gfx_watch_path}")
        logger.info(f"Queue DB: {self.settings.queue_db_path}")

        # Ensure directories exist
        Path(self.settings.queue_db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self._queue = LocalQueue(
            db_path=self.settings.queue_db_path,
            max_retries=self.settings.max_retries,
        )

        self._sync_service = SyncService(
            settings=self.settings,
            local_queue=self._queue,
        )

        # Health check
        is_healthy = await self._sync_service.health_check()
        if is_healthy:
            logger.info("Supabase connection: OK")
        else:
            logger.warning("Supabase connection: FAILED - will queue files offline")

        # Start file watcher
        self._watcher = GFXFileWatcher(
            settings=self.settings,
            sync_service=self._sync_service,
        )

        self._running = True
        logger.info("GFX Sync Agent started successfully")

        # Run main loop using watcher's run_forever
        await self._watcher.run_forever()

    async def stop(self) -> None:
        """Stop the sync agent gracefully."""
        logger.info("Stopping GFX Sync Agent...")
        self._running = False

        if self._watcher:
            await self._watcher.stop()

        logger.info("GFX Sync Agent stopped")


async def main(config_path: str | None = None) -> None:
    """Main entry point."""
    settings = load_settings(config_path)
    setup_logging(settings)

    app = SyncAgentApp(settings)

    # Setup signal handlers
    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal...")
        asyncio.create_task(app.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for all signals
            pass

    try:
        await app.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise
    finally:
        await app.stop()


def cli() -> None:
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="GFX Sync Agent - Sync PokerGFX JSON files to Supabase"
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to config.env file",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="GFX Sync Agent 1.0.0",
    )

    args = parser.parse_args()

    asyncio.run(main(config_path=args.config))


if __name__ == "__main__":
    cli()
