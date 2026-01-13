"""JSON file watcher for NAS-based PokerGFX data processing."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles  # type: ignore[import-untyped]
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from src.models.hand import HandResult
from src.primary.pokergfx_file_parser import PokerGFXFileParser

if TYPE_CHECKING:
    from src.config.settings import PokerGFXSettings
    from src.database.supabase_client import SupabaseManager
    from src.database.supabase_repository import (
        GFXHandsRepository,
        GFXSessionRepository,
        SyncLogRepository,
    )

logger = logging.getLogger(__name__)


class FileEvent:
    """Represents a file system event with type information."""

    __slots__ = ("filepath", "event_type", "timestamp")

    def __init__(self, filepath: str, event_type: str) -> None:
        self.filepath = filepath
        self.event_type = event_type  # "created" | "modified"
        self.timestamp = datetime.now()


class JSONFileHandler(FileSystemEventHandler):
    """Handles file system events for JSON files with debounce support."""

    def __init__(
        self,
        callback: asyncio.Queue[FileEvent],
        loop: asyncio.AbstractEventLoop,
        file_pattern: str = "*.json",
        debounce_seconds: float = 1.0,
    ):
        super().__init__()
        self.callback_queue = callback
        self.loop = loop
        self.file_pattern = file_pattern
        self.debounce_seconds = debounce_seconds
        # Track pending events for debounce: filepath -> (event_type, timer_handle)
        self._pending_events: dict[str, tuple[str, asyncio.TimerHandle | None]] = {}
        self._lock = threading.Lock()

    def _schedule_event(self, filepath: str, event_type: str) -> None:
        """Schedule an event with debounce.

        If multiple events occur for the same file within debounce_seconds,
        only the last event is processed.
        """
        with self._lock:
            # Cancel existing timer if any
            if filepath in self._pending_events:
                _, old_handle = self._pending_events[filepath]
                if old_handle is not None:
                    old_handle.cancel()

            # Schedule new event after debounce delay
            def emit_event() -> None:
                with self._lock:
                    if filepath in self._pending_events:
                        stored_type, _ = self._pending_events.pop(filepath)
                        event = FileEvent(filepath, stored_type)
                        self.callback_queue.put_nowait(event)
                        logger.debug(
                            f"Emitted {stored_type} event for: {Path(filepath).name}"
                        )

            handle = self.loop.call_later(self.debounce_seconds, emit_event)
            self._pending_events[filepath] = (event_type, handle)

    def _handle_event(self, event: FileSystemEvent, event_type: str) -> None:
        """Common handler for file events."""
        if event.is_directory:
            return

        src_path: str | bytes = event.src_path
        filepath = Path(src_path if isinstance(src_path, str) else src_path.decode())

        # Check if file matches pattern
        if not filepath.match(self.file_pattern):
            return

        logger.debug(f"Detected {event_type} file: {filepath}")

        # Schedule with debounce (thread-safe via loop.call_soon_threadsafe)
        self.loop.call_soon_threadsafe(
            self._schedule_event,
            str(filepath),
            event_type,
        )

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        self._handle_event(event, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        self._handle_event(event, "modified")


class JSONFileWatcher:
    """Watches NAS folder for PokerGFX JSON files and yields HandResults.

    Uses PollingObserver for SMB/CIFS network share compatibility.
    Provides same interface as PokerGFXClient for seamless integration.

    Usage:
        watcher = JSONFileWatcher(settings)
        async for result in watcher.listen():
            process(result)
    """

    def __init__(self, settings: PokerGFXSettings):
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

    async def _wait_for_file_ready(
        self, path: Path, max_retries: int = 5
    ) -> bool:
        """Wait for file to finish writing by checking size stability.

        This helps avoid reading files that are still being written,
        especially on SMB/NAS where file locks may not be properly signaled.

        Args:
            path: Path to the file
            max_retries: Maximum number of retry attempts

        Returns:
            True if file is ready (size stable), False otherwise
        """
        delay = self.settings.file_settle_delay

        for attempt in range(max_retries):
            try:
                # Check if file exists
                if not path.exists():
                    logger.warning(f"File disappeared: {path.name}")
                    return False

                # Get initial size
                size1 = path.stat().st_size

                # Wait for settle delay
                await asyncio.sleep(delay)

                # Check size again
                size2 = path.stat().st_size

                # If size is stable and non-zero, file is ready
                if size1 == size2 and size2 > 0:
                    logger.debug(
                        f"File ready after {attempt + 1} attempt(s): {path.name}"
                    )
                    return True

                # Size still changing, increase delay for next attempt
                logger.debug(
                    f"File size changed ({size1} -> {size2}), "
                    f"retrying... ({attempt + 1}/{max_retries})"
                )
                delay = min(delay * 1.5, 5.0)  # Cap at 5 seconds

            except PermissionError as e:
                # File is locked by another process
                logger.debug(
                    f"File locked (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(1.0)

            except OSError as e:
                # Network error or other I/O issue
                logger.warning(
                    f"OS error checking file (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(1.0)

        logger.warning(f"File not ready after {max_retries} attempts: {path.name}")
        return False

    async def _check_nas_connection(self) -> bool:
        """Verify NAS folder is accessible with 3-stage verification.

        Stage 1: Path existence check
        Stage 2: Directory read test
        Stage 3: Write test (optional, read-only mount OK)

        Returns:
            True if accessible (read at minimum)
        """
        watch_path = Path(self.settings.json_watch_path)

        # Stage 1: Path existence
        try:
            if not watch_path.exists():
                logger.error(f"Watch path does not exist: {watch_path}")
                return False
        except OSError as e:
            logger.error(f"Path access error (Stage 1): {e}")
            return False

        # Stage 2: Directory read test
        try:
            files = list(watch_path.iterdir())
            logger.debug(f"NAS connection verified: {len(files)} items found")
        except PermissionError as e:
            logger.error(f"Read permission denied (Stage 2): {e}")
            return False
        except OSError as e:
            logger.error(f"Directory read error (Stage 2): {e}")
            return False

        # Stage 3: Write test (optional - read-only mount is acceptable)
        test_file = watch_path / ".nas_health_check"
        try:
            test_file.touch()
            test_file.unlink()
            logger.debug("NAS write test passed")
        except (PermissionError, OSError):
            # Read-only mount is OK for watching
            logger.debug("NAS write test failed (read-only OK)")

        return True

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

        # Wait for file to finish writing (NAS write delay with retry)
        if not await self._wait_for_file_ready(path):
            logger.warning(f"Skipping file not ready for reading: {filename}")
            return []

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
        file_queue: asyncio.Queue[FileEvent] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        # Setup watchdog with polling observer (required for SMB)
        handler = JSONFileHandler(
            callback=file_queue,
            loop=loop,
            file_pattern=self.settings.file_pattern,
            debounce_seconds=1.0,
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

            # Then watch for new files with auto-reconnect
            reconnect_delay = 5.0
            max_reconnect_delay = 60.0
            consecutive_failures = 0
            max_failures = self.settings.max_reconnect_attempts

            while self._running:
                try:
                    # Wait for new file event with timeout
                    file_event = await asyncio.wait_for(
                        file_queue.get(),
                        timeout=1.0,
                    )

                    # Reset failure count on successful file receipt
                    consecutive_failures = 0
                    reconnect_delay = 5.0

                    # Process the file (JSONFileWatcher ignores event_type)
                    results = await self._process_file(file_event.filepath)
                    for result in results:
                        yield result

                except TimeoutError:
                    # Periodic health check
                    if not await self._check_nas_connection():
                        consecutive_failures += 1
                        logger.warning(
                            f"NAS connection lost ({consecutive_failures}/{max_failures}), "
                            f"retrying in {reconnect_delay}s..."
                        )

                        if consecutive_failures >= max_failures:
                            logger.error(
                                f"NAS connection failed {max_failures} times. "
                                f"Consider switching to fallback mode."
                            )
                            # Don't stop - keep trying but with max delay
                            consecutive_failures = max_failures

                        await asyncio.sleep(reconnect_delay)
                        # Exponential backoff
                        reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    else:
                        # Reset on successful check
                        if consecutive_failures > 0:
                            logger.info("NAS connection restored")
                            consecutive_failures = 0
                            reconnect_delay = 5.0
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

    def get_stats(self) -> dict[str, object]:
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


class SupabaseJSONFileWatcher:
    """Watches NAS folder and syncs PokerGFX JSON files to Supabase.

    Key differences from JSONFileWatcher:
    - Duplicate detection via Supabase (file_hash) instead of local JSON
    - Raw JSON stored in Supabase JSONB for flexibility
    - Sync logging for audit trail
    - Incremental sync: on file modification, only new hands are added

    Usage:
        watcher = SupabaseJSONFileWatcher(
            settings, supabase, session_repo, sync_log_repo, hands_repo
        )
        async for result in watcher.listen():
            process(result)
    """

    def __init__(
        self,
        settings: PokerGFXSettings,
        supabase: SupabaseManager,
        session_repo: GFXSessionRepository,
        sync_log_repo: SyncLogRepository,
        hands_repo: GFXHandsRepository | None = None,
    ) -> None:
        """Initialize Supabase file watcher.

        Args:
            settings: PokerGFX settings with json_watch_path
            supabase: Supabase manager instance
            session_repo: GFX session repository
            sync_log_repo: Sync log repository
            hands_repo: GFX hands repository (optional, for incremental sync)
        """
        self.settings = settings
        self.supabase = supabase
        self.session_repo = session_repo
        self.sync_log_repo = sync_log_repo
        self.hands_repo = hands_repo
        self.parser = PokerGFXFileParser()
        self._running = False
        self._observer: PollingObserver | None = None

    async def _compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of file content.

        Args:
            filepath: Path to the file

        Returns:
            Hexadecimal SHA256 hash string
        """
        import hashlib

        async with aiofiles.open(filepath, "rb") as f:
            content = await f.read()
        return hashlib.sha256(content).hexdigest()

    async def _wait_for_file_ready(
        self, path: Path, max_retries: int = 5
    ) -> bool:
        """Wait for file to finish writing by checking size stability.

        This helps avoid reading files that are still being written,
        especially on SMB/NAS where file locks may not be properly signaled.

        Args:
            path: Path to the file
            max_retries: Maximum number of retry attempts

        Returns:
            True if file is ready (size stable), False otherwise
        """
        delay = self.settings.file_settle_delay

        for attempt in range(max_retries):
            try:
                if not path.exists():
                    logger.warning(f"File disappeared: {path.name}")
                    return False

                size1 = path.stat().st_size
                await asyncio.sleep(delay)
                size2 = path.stat().st_size

                if size1 == size2 and size2 > 0:
                    logger.debug(
                        f"File ready after {attempt + 1} attempt(s): {path.name}"
                    )
                    return True

                logger.debug(
                    f"File size changed ({size1} -> {size2}), "
                    f"retrying... ({attempt + 1}/{max_retries})"
                )
                delay = min(delay * 1.5, 5.0)

            except PermissionError as e:
                logger.debug(
                    f"File locked (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(1.0)

            except OSError as e:
                logger.warning(
                    f"OS error checking file (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(1.0)

        logger.warning(f"File not ready after {max_retries} attempts: {path.name}")
        return False

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
            list(watch_path.iterdir())
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Cannot access watch path: {e}")
            return False

    async def _process_file(
        self, filepath: str, event_type: str = "created"
    ) -> list[HandResult]:
        """Process a single JSON file and sync to Supabase.

        For 'created' events: saves full session and all hands.
        For 'modified' events: saves only new hands (incremental sync).

        Args:
            filepath: Path to the JSON file
            event_type: Type of file event ("created" or "modified")

        Returns:
            List of HandResult objects from the file (new hands only for modified)
        """
        path = Path(filepath)
        filename = path.name

        # Wait for file to finish writing (NAS write delay with retry)
        if not await self._wait_for_file_ready(path):
            logger.warning(f"Skipping file not ready for reading: {filename}")
            return []

        sync_log: dict[str, Any] | None = None

        try:
            # Compute hash for duplicate detection
            file_hash = await self._compute_file_hash(path)

            # Read and parse file first (needed for both created and modified)
            async with aiofiles.open(filepath, encoding="utf-8") as f:
                content = await f.read()

            data = json.loads(content)
            session_id = data.get("ID", 0)
            all_hands = data.get("Hands", [])

            # Handle based on event type
            if event_type == "modified":
                return await self._handle_modified_file(
                    path, filename, file_hash, data, session_id, all_hands
                )

            # === CREATED event: Full sync ===

            # Check if already processed (via Supabase)
            if await self.sync_log_repo.is_file_processed(file_hash):
                logger.debug(f"Skipping already processed file: {filename}")
                return []

            # Log sync start
            file_size = path.stat().st_size
            sync_log = await self.sync_log_repo.log_sync_start(
                file_name=filename,
                file_path=str(path),
                file_hash=file_hash,
                file_size_bytes=file_size,
                operation="created",
            )

            # Save raw JSON to Supabase
            session_record = await self.session_repo.save_session(
                session_id=session_id,
                file_name=filename,
                file_hash=file_hash,
                raw_json=data,
                nas_path=str(path),
            )

            if session_record is None:
                # Duplicate detected
                await self.sync_log_repo.log_sync_complete(
                    log_id=sync_log["id"],
                    status="skipped",
                    error_message="Duplicate session",
                )
                return []

            # Save individual hands if hands_repo is available
            if self.hands_repo and all_hands:
                await self.hands_repo.save_hands(session_id, all_hands)

            # Parse HandResults for downstream processing
            results = self.parser.parse_session_data(data)

            # Log success
            await self.sync_log_repo.log_sync_complete(
                log_id=sync_log["id"],
                session_id=session_record["id"],
                status="success",
            )

            logger.info(
                f"Synced {filename} to Supabase: {len(results)} hand results, "
                f"session_id={session_id}, hands={len(all_hands)}"
            )

            return results

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filename}: {e}")
            if sync_log:
                await self.sync_log_repo.log_sync_complete(
                    log_id=sync_log["id"],
                    status="failed",
                    error_message=f"JSON decode error: {e}",
                )
            return []

        except Exception as e:
            logger.exception(f"Error processing {filename}: {e}")
            if sync_log:
                await self.sync_log_repo.log_sync_complete(
                    log_id=sync_log["id"],
                    status="failed",
                    error_message=str(e),
                )
            return []

    async def _handle_modified_file(
        self,
        path: Path,
        filename: str,
        file_hash: str,
        data: dict[str, Any],
        session_id: int,
        all_hands: list[dict[str, Any]],
    ) -> list[HandResult]:
        """Handle file modification: save only new hands.

        Args:
            path: Path to the file
            filename: File name
            file_hash: New file hash
            data: Parsed JSON data
            session_id: PokerGFX session ID
            all_hands: All hands from the file

        Returns:
            List of HandResult objects for new hands only
        """
        sync_log: dict[str, Any] | None = None

        try:
            # Check if session exists
            existing_session = await self.session_repo.get_by_session_id(session_id)

            if not existing_session:
                # Session doesn't exist yet, treat as created
                logger.info(
                    f"Modified file {filename} has no existing session, "
                    f"treating as new file"
                )
                # Recursively call with "created" event type
                return await self._process_file(str(path), "created")

            # Log sync start for modification
            file_size = path.stat().st_size
            sync_log = await self.sync_log_repo.log_sync_start(
                file_name=filename,
                file_path=str(path),
                file_hash=file_hash,
                file_size_bytes=file_size,
                operation="modified",
            )

            # Find new hands only
            new_hands: list[dict[str, Any]] = []
            if self.hands_repo:
                new_hands = await self.hands_repo.get_new_hands(session_id, all_hands)
            else:
                # Without hands_repo, we can't do incremental sync
                logger.warning(
                    f"hands_repo not available, skipping incremental sync for {filename}"
                )
                await self.sync_log_repo.log_sync_complete(
                    log_id=sync_log["id"],
                    status="skipped",
                    error_message="hands_repo not configured for incremental sync",
                )
                return []

            if not new_hands:
                logger.debug(f"No new hands in modified file: {filename}")
                await self.sync_log_repo.log_sync_complete(
                    log_id=sync_log["id"],
                    status="skipped",
                    error_message="No new hands found",
                )
                return []

            # Save new hands
            await self.hands_repo.save_hands(session_id, new_hands)

            # Update session with new data
            await self.session_repo.update_session(
                session_id=session_id,
                raw_json=data,
                file_hash=file_hash,
            )

            # Parse HandResults for new hands only
            # Create a temporary data dict with only new hands for parsing
            temp_data = {**data, "Hands": new_hands}
            results = self.parser.parse_session_data(temp_data)

            # Log success
            await self.sync_log_repo.log_sync_complete(
                log_id=sync_log["id"],
                session_id=existing_session["id"],
                status="success",
            )

            logger.info(
                f"Incremental sync {filename}: {len(new_hands)} new hands added, "
                f"session_id={session_id}, total_hands={len(all_hands)}"
            )

            return results

        except Exception as e:
            logger.exception(f"Error handling modified file {filename}: {e}")
            if sync_log:
                await self.sync_log_repo.log_sync_complete(
                    log_id=sync_log["id"],
                    status="failed",
                    error_message=str(e),
                )
            return []

    async def _process_existing_files(self) -> AsyncIterator[HandResult]:
        """Process any existing unprocessed files in the watch folder.

        Yields:
            HandResult objects from existing files
        """
        watch_path = Path(self.settings.json_watch_path)

        for filepath in watch_path.glob(self.settings.file_pattern):
            if not self._running:
                break

            results = await self._process_file(str(filepath))
            for result in results:
                yield result

    async def listen(self) -> AsyncIterator[HandResult]:
        """Listen for new JSON files and yield HandResults.

        Compatible with JSONFileWatcher.listen() interface.

        Yields:
            HandResult objects as files are detected and processed
        """
        # Verify NAS connection
        if not await self._check_nas_connection():
            raise RuntimeError(
                f"Cannot access watch path: {self.settings.json_watch_path}"
            )

        # Verify Supabase connection
        if not await self.supabase.health_check():
            raise RuntimeError("Supabase connection failed")

        self._running = True
        logger.info(
            f"Starting Supabase file watcher on: {self.settings.json_watch_path}"
        )

        # Create async queue for file events
        file_queue: asyncio.Queue[FileEvent] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        # Setup watchdog with polling observer (required for SMB)
        handler = JSONFileHandler(
            callback=file_queue,
            loop=loop,
            file_pattern=self.settings.file_pattern,
            debounce_seconds=1.0,
        )

        self._observer = PollingObserver(timeout=self.settings.polling_interval)
        self._observer.schedule(
            handler,
            self.settings.json_watch_path,
            recursive=False,
        )
        self._observer.start()

        logger.info(
            f"Supabase file watcher started "
            f"(polling interval: {self.settings.polling_interval}s)"
        )

        try:
            # First, process any existing unprocessed files
            async for result in self._process_existing_files():
                if not self._running:
                    break
                yield result

            # Then watch for new/modified files
            while self._running:
                try:
                    file_event = await asyncio.wait_for(
                        file_queue.get(),
                        timeout=1.0,
                    )

                    results = await self._process_file(
                        file_event.filepath, file_event.event_type
                    )
                    for result in results:
                        yield result

                except TimeoutError:
                    # Periodically check connections
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

        logger.info("Supabase file watcher stopped")

    async def disconnect(self) -> None:
        """Alias for stop() - compatibility interface."""
        await self.stop()

    def get_stats(self) -> dict[str, object]:
        """Get watcher statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "watch_path": self.settings.json_watch_path,
            "polling_interval": self.settings.polling_interval,
            "is_running": self._running,
            "backend": "supabase",
        }
