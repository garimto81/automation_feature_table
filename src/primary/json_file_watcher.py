"""JSON file watcher for NAS-based PokerGFX data processing."""

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from src.models.hand import HandResult
from src.primary.pokergfx_file_parser import PokerGFXFileParser

if TYPE_CHECKING:
    from src.config.settings import PokerGFXSettings

logger = logging.getLogger(__name__)


class JSONFileHandler(FileSystemEventHandler):
    """Handles file system events for JSON files."""

    def __init__(
        self,
        callback: "asyncio.Queue[str]",
        loop: asyncio.AbstractEventLoop,
        file_pattern: str = "*.json",
    ):
        super().__init__()
        self.callback_queue = callback
        self.loop = loop
        self.file_pattern = file_pattern

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        filepath = Path(event.src_path)

        # Check if file matches pattern
        if not filepath.match(self.file_pattern):
            return

        logger.debug(f"Detected new file: {filepath}")

        # Put filepath into async queue (thread-safe)
        self.loop.call_soon_threadsafe(
            self.callback_queue.put_nowait,
            str(filepath),
        )


class JSONFileWatcher:
    """Watches NAS folder for PokerGFX JSON files and yields HandResults.

    Uses PollingObserver for SMB/CIFS network share compatibility.
    Provides same interface as PokerGFXClient for seamless integration.

    Usage:
        watcher = JSONFileWatcher(settings)
        async for result in watcher.listen():
            process(result)
    """

    def __init__(self, settings: "PokerGFXSettings"):
        """Initialize watcher.

        Args:
            settings: PokerGFX settings with json_watch_path configured
        """
        self.settings = settings
        self.parser = PokerGFXFileParser()
        self._running = False
        self._observer: PollingObserver | None = None
        self._processed_files: set[str] = set()
        self._lock = threading.Lock()

        # Load previously processed files
        self._load_processed_files()

    def _load_processed_files(self) -> None:
        """Load processed files list from disk."""
        db_path = Path(self.settings.processed_db_path)
        if db_path.exists():
            try:
                with open(db_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self._processed_files = set(data.get("files", []))
                    logger.info(
                        f"Loaded {len(self._processed_files)} processed files from DB"
                    )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not load processed files DB: {e}")
                self._processed_files = set()
        else:
            self._processed_files = set()

    def _save_processed_file(self, filename: str) -> None:
        """Save a processed file to the database.

        Args:
            filename: Name of the processed file
        """
        with self._lock:
            self._processed_files.add(filename)

            db_path = Path(self.settings.processed_db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                data = {
                    "files": list(self._processed_files),
                    "last_updated": datetime.now().isoformat(),
                }
                with open(db_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except OSError as e:
                logger.error(f"Could not save processed files DB: {e}")

    def _is_processed(self, filename: str) -> bool:
        """Check if a file has already been processed.

        Args:
            filename: Name of the file

        Returns:
            True if already processed
        """
        return filename in self._processed_files

    async def _check_nas_connection(self) -> bool:
        """Verify NAS folder is accessible.

        Returns:
            True if accessible
        """
        watch_path = Path(self.settings.json_watch_path)

        if not watch_path.exists():
            logger.error(f"Watch path does not exist: {watch_path}")
            return False

        try:
            # Try to list directory contents
            list(watch_path.iterdir())
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Cannot access watch path: {e}")
            return False

    async def _process_file(self, filepath: str) -> list[HandResult]:
        """Process a single JSON file.

        Args:
            filepath: Path to the JSON file

        Returns:
            List of HandResult objects from the file
        """
        path = Path(filepath)
        filename = path.name

        # Check if already processed
        if self._is_processed(filename):
            logger.debug(f"Skipping already processed file: {filename}")
            return []

        # Wait for file to finish writing (NAS write delay)
        await asyncio.sleep(self.settings.file_settle_delay)

        try:
            # Read file asynchronously
            async with aiofiles.open(filepath, encoding="utf-8") as f:
                content = await f.read()

            data = json.loads(content)

            # Parse and get results
            results = self.parser.parse_session_data(data)

            # Mark as processed
            self._save_processed_file(filename)

            logger.info(
                f"Processed {filename}: {len(results)} hand results, "
                f"{len(data.get('Hands', []))} hands in session"
            )

            return results

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filename}: {e}")
            await self._move_to_error_folder(path)
            return []

        except OSError as e:
            logger.error(f"Could not read file {filename}: {e}")
            return []

        except Exception as e:
            logger.exception(f"Unexpected error processing {filename}: {e}")
            return []

    async def _move_to_error_folder(self, filepath: Path) -> None:
        """Move corrupted file to error folder.

        Args:
            filepath: Path to the file
        """
        try:
            error_dir = filepath.parent / "errors"
            error_dir.mkdir(exist_ok=True)

            dest = error_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filepath.name}"

            # Use sync operation in executor (aiofiles doesn't have move)
            await asyncio.get_event_loop().run_in_executor(
                None, filepath.rename, dest
            )

            logger.warning(f"Moved corrupted file to: {dest}")
        except OSError as e:
            logger.error(f"Could not move file to error folder: {e}")

    async def _process_existing_files(self) -> AsyncIterator[HandResult]:
        """Process any existing unprocessed files in the watch folder.

        Yields:
            HandResult objects from existing files
        """
        watch_path = Path(self.settings.json_watch_path)

        for filepath in watch_path.glob(self.settings.file_pattern):
            if self._is_processed(filepath.name):
                continue

            results = await self._process_file(str(filepath))
            for result in results:
                yield result

    async def listen(self) -> AsyncIterator[HandResult]:
        """Listen for new JSON files and yield HandResults.

        This is the main entry point, compatible with PokerGFXClient.listen().

        Yields:
            HandResult objects as files are detected and processed
        """
        # Verify NAS connection
        if not await self._check_nas_connection():
            raise RuntimeError(
                f"Cannot access watch path: {self.settings.json_watch_path}"
            )

        self._running = True
        logger.info(f"Starting file watcher on: {self.settings.json_watch_path}")

        # Create async queue for file events
        file_queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        # Setup watchdog with polling observer (required for SMB)
        handler = JSONFileHandler(
            callback=file_queue,
            loop=loop,
            file_pattern=self.settings.file_pattern,
        )

        self._observer = PollingObserver(timeout=self.settings.polling_interval)
        self._observer.schedule(
            handler,
            self.settings.json_watch_path,
            recursive=False,
        )
        self._observer.start()

        logger.info(
            f"File watcher started (polling interval: {self.settings.polling_interval}s)"
        )

        try:
            # First, process any existing unprocessed files
            async for result in self._process_existing_files():
                if not self._running:
                    break
                yield result

            # Then watch for new files
            while self._running:
                try:
                    # Wait for new file with timeout
                    filepath = await asyncio.wait_for(
                        file_queue.get(),
                        timeout=1.0,
                    )

                    # Process the file
                    results = await self._process_file(filepath)
                    for result in results:
                        yield result

                except TimeoutError:
                    # Check if NAS is still accessible periodically
                    if not await self._check_nas_connection():
                        logger.warning("NAS connection lost, attempting to reconnect...")
                        await asyncio.sleep(5.0)
                    continue

        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the file watcher."""
        self._running = False

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        logger.info("File watcher stopped")

    async def disconnect(self) -> None:
        """Alias for stop() - compatibility with PokerGFXClient interface."""
        await self.stop()

    def get_stats(self) -> dict:
        """Get watcher statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "processed_files_count": len(self._processed_files),
            "watch_path": self.settings.json_watch_path,
            "polling_interval": self.settings.polling_interval,
            "is_running": self._running,
        }
