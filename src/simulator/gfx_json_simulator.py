"""GFX JSON Simulator for NAS testing.

Simulates real-time hand generation by creating cumulative JSON files
at specified intervals.
"""

from __future__ import annotations

import argparse
import asyncio
import errno
import json
import logging
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict

from src.simulator.config import SimulatorSettings, get_simulator_settings
from src.simulator.hand_splitter import HandSplitter
from src.simulator.history import (
    CheckpointData,
    FileProcessingRecord,
    FileStatus,
    HistoryManager,
    RunMode,
    SessionStatus,
    SimulationSession,
    get_history_manager,
)

logger = logging.getLogger(__name__)


# Type definitions for better type safety
class CheckpointDict(TypedDict):
    """Type for checkpoint dictionary."""

    file_index: int
    hand_index: int
    timestamp: str


class SimulationMetrics(TypedDict):
    """Metrics for simulation performance monitoring."""

    files_processed: int
    total_hands_processed: int
    avg_hand_processing_time_ms: float
    error_count: int
    retry_count: int


class Status(Enum):
    """Simulator status."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class LogEntry:
    """Log entry for simulator events."""

    timestamp: datetime
    level: str
    message: str
    table_name: str = ""

    @property
    def icon(self) -> str:
        """Get icon based on log level."""
        icons = {
            "INFO": "OK",
            "WARNING": "WARN",
            "ERROR": "ERR",
            "SUCCESS": "OK",
        }
        return icons.get(self.level, "INFO")

    def __str__(self) -> str:
        """Format log entry as string."""
        ts = self.timestamp.strftime("%H:%M:%S")
        table = f" ({self.table_name})" if self.table_name else ""
        return f"[{ts}] {self.icon} {self.message}{table}"


@dataclass
class SimulationProgress:
    """Progress tracking for simulation."""

    current_hand: int = 0
    total_hands: int = 0
    start_time: datetime | None = None
    current_file: str = ""

    @property
    def progress(self) -> float:
        """Get progress as percentage (0.0 to 1.0)."""
        if self.total_hands == 0:
            return 0.0
        return self.current_hand / self.total_hands

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def remaining_seconds(self) -> float:
        """Estimate remaining time in seconds."""
        if self.current_hand == 0 or self.total_hands == 0:
            return 0.0
        elapsed = self.elapsed_seconds
        rate = elapsed / self.current_hand
        remaining_hands = self.total_hands - self.current_hand
        return rate * remaining_hands


@dataclass
class SimulationCheckpoint:
    """Checkpoint for pause/resume functionality."""

    file_index: int = 0
    hand_index: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> CheckpointDict:
        """Convert to dictionary."""
        return CheckpointDict(
            file_index=self.file_index,
            hand_index=self.hand_index,
            timestamp=self.timestamp.isoformat(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationCheckpoint:
        """Create from dictionary."""
        return cls(
            file_index=data.get("file_index", 0),
            hand_index=data.get("hand_index", 0),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
        )


@dataclass
class GFXJsonSimulator:
    """Simulator for generating cumulative GFX JSON files.

    Thread-safety: Progress updates are protected by _progress_lock.
    Memory: Logs use deque with maxlen for efficient circular buffer.
    """

    source_path: Path
    target_path: Path
    interval: int = 60
    settings: SimulatorSettings = field(default_factory=get_simulator_settings)
    run_mode: RunMode = RunMode.ALL

    # History management
    history_manager: HistoryManager = field(default_factory=get_history_manager)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # State
    status: Status = field(default=Status.IDLE, init=False)
    progress: SimulationProgress = field(
        default_factory=SimulationProgress, init=False
    )
    # Use deque for memory-efficient log rotation (O(1) instead of O(n))
    logs: deque[LogEntry] = field(
        default_factory=lambda: deque(maxlen=100), init=False
    )
    _stop_requested: bool = field(default=False, init=False)
    _selected_files: list[Path] = field(default_factory=list, init=False)
    _pause_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _checkpoint: SimulationCheckpoint = field(
        default_factory=SimulationCheckpoint, init=False
    )
    _file_start_times: dict[str, datetime] = field(default_factory=dict, init=False)
    _last_checkpoint_save: float = field(default=0.0, init=False)
    # Thread safety for progress updates
    _progress_lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    # Performance metrics
    _metrics: SimulationMetrics = field(
        default_factory=lambda: SimulationMetrics(
            files_processed=0,
            total_hands_processed=0,
            avg_hand_processing_time_ms=0.0,
            error_count=0,
            retry_count=0,
        ),
        init=False,
    )
    _hand_processing_times: list[float] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Initialize after dataclass creation."""
        # Set event initially (not paused)
        self._pause_event.set()

    def _log(
        self,
        message: str,
        level: str = "INFO",
        table_name: str = "",
    ) -> None:
        """Add log entry.

        Thread-safe: deque.append() is atomic in CPython.
        Memory-efficient: deque(maxlen=100) auto-rotates.
        """
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            table_name=table_name,
        )
        # deque(maxlen=100) auto-rotates, no manual slicing needed (O(1))
        self.logs.append(entry)

        # Also log to console
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(str(entry))

    def stop(self) -> None:
        """Request simulation stop."""
        self._stop_requested = True
        self.status = Status.STOPPED
        self._log("Simulation stopped by user", "WARNING")

    def pause(self) -> None:
        """Pause simulation.

        The simulation will pause after the current hand completes.
        """
        if self.status == Status.RUNNING:
            self._pause_event.clear()
            self.status = Status.PAUSED
            self._log("Simulation paused", "WARNING")

    def resume(self) -> None:
        """Resume paused simulation."""
        if self.status == Status.PAUSED:
            self._pause_event.set()
            self.status = Status.RUNNING
            self._log("Simulation resumed", "INFO")

    async def _wait_if_paused(self) -> None:
        """Wait if simulation is paused."""
        await self._pause_event.wait()

    def get_checkpoint(self) -> SimulationCheckpoint:
        """Get current checkpoint for pause/resume."""
        return self._checkpoint

    def check_file_status(self, file_path: Path) -> tuple[FileStatus, datetime | None]:
        """Check if file has been processed and get last processing time.

        Args:
            file_path: Path to check.

        Returns:
            Tuple of (FileStatus, last_processed_at or None).
        """
        if not self.settings.history_enabled:
            return FileStatus.NEW, None

        status, record = self.history_manager.get_file_status(
            str(self.source_path), file_path
        )
        last_processed = record.processed_at if record else None
        return status, last_processed

    def _save_checkpoint_debounced(self) -> None:
        """Save checkpoint with debounce (every 5 seconds max)."""
        if not self.settings.history_enabled:
            return

        now = time.time()
        if now - self._last_checkpoint_save >= 5.0:
            checkpoint_data = CheckpointData(
                session_id=self.session_id,
                file_index=self._checkpoint.file_index,
                hand_index=self._checkpoint.hand_index,
                timestamp=self._checkpoint.timestamp,
            )
            self.history_manager.save_checkpoint(checkpoint_data)
            self._last_checkpoint_save = now

    def _create_session(self, files_total: int) -> None:
        """Create and save simulation session."""
        if not self.settings.history_enabled:
            return

        session = SimulationSession(
            session_id=self.session_id,
            started_at=datetime.now(),
            ended_at=None,
            source_path=str(self.source_path),
            target_path=str(self.target_path),
            files_total=files_total,
            files_completed=0,
            status=SessionStatus.RUNNING.value,
        )
        self.history_manager.add_session(session)

    def _update_session(
        self,
        files_completed: int,
        status: SessionStatus,
    ) -> None:
        """Update session status."""
        if not self.settings.history_enabled:
            return

        session = SimulationSession(
            session_id=self.session_id,
            started_at=self.progress.start_time or datetime.now(),
            ended_at=datetime.now() if status != SessionStatus.RUNNING else None,
            source_path=str(self.source_path),
            target_path=str(self.target_path),
            files_total=self.progress.total_hands,
            files_completed=files_completed,
            status=status.value,
        )
        self.history_manager.add_session(session)

    def _add_file_record(
        self,
        file_path: Path,
        hand_count: int,
        status: str,
    ) -> None:
        """Add file processing record."""
        if not self.settings.history_enabled:
            return

        start_time = self._file_start_times.get(str(file_path), datetime.now())
        duration = (datetime.now() - start_time).total_seconds()

        record = FileProcessingRecord(
            file_path=str(file_path),
            file_hash=self.history_manager.calculate_file_hash(file_path),
            processed_at=datetime.now(),
            hand_count=hand_count,
            duration_sec=duration,
            status=status,
            session_id=self.session_id,
        )
        self.history_manager.add_record(str(self.source_path), record)

    def get_logs(self, limit: int = 20) -> list[LogEntry]:
        """Get recent logs."""
        return list(self.logs)[-limit:]

    def get_metrics(self) -> SimulationMetrics:
        """Get current simulation metrics."""
        with self._progress_lock:
            return SimulationMetrics(
                files_processed=self._metrics["files_processed"],
                total_hands_processed=self._metrics["total_hands_processed"],
                avg_hand_processing_time_ms=self._metrics["avg_hand_processing_time_ms"],
                error_count=self._metrics["error_count"],
                retry_count=self._metrics["retry_count"],
            )

    def _update_metrics(
        self,
        *,
        hand_time_ms: float | None = None,
        file_completed: bool = False,
        error: bool = False,
        retry: bool = False,
    ) -> None:
        """Update simulation metrics thread-safely."""
        with self._progress_lock:
            if hand_time_ms is not None:
                self._hand_processing_times.append(hand_time_ms)
                self._metrics["total_hands_processed"] += 1
                # Keep rolling average
                if self._hand_processing_times:
                    self._metrics["avg_hand_processing_time_ms"] = (
                        sum(self._hand_processing_times) / len(self._hand_processing_times)
                    )
            if file_completed:
                self._metrics["files_processed"] += 1
            if error:
                self._metrics["error_count"] += 1
            if retry:
                self._metrics["retry_count"] += 1

    def _write_with_retry(self, path: Path, content: str) -> bool:
        """Write file with retry logic.

        Handles specific OS errors:
        - PermissionError: Access denied (no retry)
        - ENOSPC: No space left on device (no retry)
        - EROFS: Read-only file system (no retry)
        - Other OSError: Retry with delay

        Args:
            path: Target file path
            content: File content

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(1, self.settings.retry_count + 1):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return True
            except PermissionError as e:
                # No point retrying permission errors
                self._log(
                    f"Permission denied (no retry): {path} - {e}",
                    "ERROR",
                )
                self._update_metrics(error=True)
                return False
            except OSError as e:
                # Handle specific OS error codes
                if e.errno == errno.ENOSPC:
                    self._log(
                        f"No disk space left on device: {path}",
                        "ERROR",
                    )
                    self._update_metrics(error=True)
                    return False
                elif e.errno == errno.EROFS:
                    self._log(
                        f"Read-only file system: {path}",
                        "ERROR",
                    )
                    self._update_metrics(error=True)
                    return False
                else:
                    # Retriable OS errors (network, temporary issues)
                    self._log(
                        f"Write failed (attempt {attempt}/{self.settings.retry_count}): {e}",
                        "WARNING",
                    )
                    self._update_metrics(retry=True)
                    if attempt < self.settings.retry_count:
                        time.sleep(self.settings.retry_delay_sec)

        self._log(f"Failed to write after {self.settings.retry_count} attempts", "ERROR")
        self._update_metrics(error=True)
        return False

    def _discover_json_files(self) -> list[Path]:
        """Discover all JSON files in source directory."""
        json_files = list(self.source_path.rglob("*.json"))
        self._log(f"Found {len(json_files)} JSON files in {self.source_path}")
        return json_files

    async def simulate_file(self, json_path: Path) -> bool:
        """Simulate single JSON file.

        Args:
            json_path: Path to source JSON file

        Returns:
            True if successful, False otherwise
        """
        # Record start time for duration calculation
        self._file_start_times[str(json_path)] = datetime.now()
        hand_count = 0

        try:
            # Read and parse JSON
            data = json.loads(json_path.read_text(encoding="utf-8"))
            hands = HandSplitter.split_hands(data)
            metadata = HandSplitter.extract_metadata(data)

            if not hands:
                self._log(f"No hands found in {json_path.name}", "WARNING")
                self._add_file_record(json_path, 0, "completed")
                return True

            hand_count = len(hands)

            # Determine relative path for output
            rel_path = json_path.relative_to(self.source_path)
            output_path = self.target_path / rel_path

            # Extract table name from path
            parts = rel_path.parts
            table_name = parts[0] if parts else ""

            self._log(
                f"Starting simulation: {rel_path} ({len(hands)} hands)",
                table_name=table_name,
            )

            # Simulate each hand
            for i in range(1, len(hands) + 1):
                hand_start_time = time.time()

                # Check for pause before processing
                await self._wait_if_paused()

                if self._stop_requested:
                    self._add_file_record(json_path, i - 1, "partial")
                    return False

                # Update checkpoint
                self._checkpoint.hand_index = i
                self._checkpoint.timestamp = datetime.now()
                self._save_checkpoint_debounced()

                # Build cumulative JSON
                cumulative = HandSplitter.build_cumulative(hands, i, metadata)
                content = json.dumps(cumulative, indent=2, ensure_ascii=False)

                # Write to target
                if not self._write_with_retry(output_path, content):
                    self.status = Status.ERROR
                    self._add_file_record(json_path, i - 1, "failed")
                    return False

                # Thread-safe progress update
                with self._progress_lock:
                    self.progress.current_hand += 1

                # Update metrics
                hand_time_ms = (time.time() - hand_start_time) * 1000
                self._update_metrics(hand_time_ms=hand_time_ms)

                self._log(f"Hand {i}/{len(hands)} generated", "SUCCESS", table_name)

                # Wait for interval (except last hand)
                if i < len(hands):
                    await asyncio.sleep(self.interval)

            self._log(f"Completed: {rel_path}", "SUCCESS", table_name)
            self._add_file_record(json_path, hand_count, "completed")
            self._update_metrics(file_completed=True)
            return True

        except json.JSONDecodeError as e:
            self._log(f"JSON parse error in {json_path.name}: {e}", "ERROR")
            self._add_file_record(json_path, 0, "failed")
            self._update_metrics(error=True)
            return False
        except PermissionError as e:
            self._log(f"Permission denied reading {json_path.name}: {e}", "ERROR")
            self._add_file_record(json_path, 0, "failed")
            self._update_metrics(error=True)
            return False
        except FileNotFoundError as e:
            self._log(f"File not found: {json_path.name}: {e}", "ERROR")
            self._add_file_record(json_path, 0, "failed")
            self._update_metrics(error=True)
            return False
        except Exception as e:
            self._log(f"Error processing {json_path.name}: {e}", "ERROR")
            self._add_file_record(json_path, hand_count, "failed")
            self._update_metrics(error=True)
            return False

    async def run(self) -> None:
        """Run simulation for all discovered JSON files."""
        self._stop_requested = False
        self.status = Status.RUNNING
        self.progress = SimulationProgress(start_time=datetime.now())

        self._log("Starting GFX JSON Simulator")
        self._log(f"Source: {self.source_path}")
        self._log(f"Target: {self.target_path}")
        self._log(f"Interval: {self.interval}s")
        self._log(f"Run mode: {self.run_mode.value}")

        # Use selected files if provided, otherwise discover
        if self._selected_files:
            json_files = list(self._selected_files)
            self._log(f"Using {len(json_files)} selected files")
        else:
            json_files = self._discover_json_files()

        if not json_files:
            self._log("No JSON files found", "WARNING")
            self.status = Status.COMPLETED
            return

        # Filter files based on run mode
        if self.run_mode == RunMode.NEW_ONLY:
            original_count = len(json_files)
            json_files = self._filter_new_files(json_files)
            filtered_count = original_count - len(json_files)
            if filtered_count > 0:
                self._log(f"Filtered {filtered_count} already processed files")

        # Create session
        self._create_session(len(json_files))

        # Calculate total hands
        total_hands = 0
        for json_path in json_files:
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                total_hands += HandSplitter.get_hand_count(data)
            except Exception:
                pass

        self.progress.total_hands = total_hands
        self._log(f"Total hands to process: {total_hands}")

        # Handle resume mode
        start_file_idx = 0
        if self.run_mode == RunMode.RESUME:
            checkpoint = self.history_manager.load_checkpoint()
            if checkpoint and checkpoint.session_id:
                start_file_idx = checkpoint.file_index
                self._log(f"Resuming from file index {start_file_idx}")

        # Process each file
        files_completed = 0
        for file_idx, json_path in enumerate(json_files[start_file_idx:], start=start_file_idx):
            # Check for pause before processing file
            await self._wait_if_paused()

            if self._stop_requested:
                self._update_session(files_completed, SessionStatus.STOPPED)
                break

            # Update checkpoint
            self._checkpoint.file_index = file_idx
            self._checkpoint.hand_index = 0

            self.progress.current_file = json_path.name
            success = await self.simulate_file(json_path)

            if success:
                files_completed += 1

            if not success and self.status == Status.ERROR:
                self._update_session(files_completed, SessionStatus.ERROR)
                break

        if not self._stop_requested and self.status != Status.ERROR:
            self.status = Status.COMPLETED
            self._update_session(files_completed, SessionStatus.COMPLETED)
            self.history_manager.clear_checkpoint()
            self._log("Simulation completed successfully", "SUCCESS")

    def _filter_new_files(self, files: list[Path]) -> list[Path]:
        """Filter to only include new/unprocessed files.

        Args:
            files: List of files to filter.

        Returns:
            List of files that haven't been processed.
        """
        new_files = []
        for f in files:
            status, _ = self.check_file_status(f)
            if status == FileStatus.NEW:
                new_files.append(f)
            elif status == FileStatus.PROCESSED_CHANGED:
                # Include changed files with warning
                self._log(
                    f"File changed since last processing: {f.name}",
                    "WARNING",
                )
                new_files.append(f)
        return new_files

    def run_sync(self) -> None:
        """Run simulation synchronously (for CLI)."""
        asyncio.run(self.run())


@dataclass
class TableSimulationTask:
    """Task for simulating a single table's files.

    Thread-safety: Progress updates are protected by _progress_lock.
    Memory: Logs use deque with maxlen for efficient circular buffer.
    """

    table_name: str
    files: list[Path]
    target_path: Path
    interval: int
    settings: SimulatorSettings = field(default_factory=get_simulator_settings)

    # State
    status: Status = field(default=Status.IDLE, init=False)
    progress: SimulationProgress = field(
        default_factory=SimulationProgress, init=False
    )
    # Use deque for memory-efficient log rotation (O(1))
    logs: deque[LogEntry] = field(
        default_factory=lambda: deque(maxlen=50), init=False
    )
    _stop_requested: bool = field(default=False, init=False)
    _progress_lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def _log(self, message: str, level: str = "INFO") -> None:
        """Add log entry (thread-safe, memory-efficient)."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            table_name=self.table_name,
        )
        # deque(maxlen=50) auto-rotates (O(1))
        self.logs.append(entry)
        logger.info(str(entry))

    def stop(self) -> None:
        """Request task stop."""
        self._stop_requested = True
        self.status = Status.STOPPED

    async def run(self) -> bool:
        """Run simulation for this table's files."""
        self.status = Status.RUNNING
        self.progress.start_time = datetime.now()
        self._log(f"Starting table {self.table_name} ({len(self.files)} files)")

        # Calculate total hands
        total_hands = 0
        for f in self.files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                total_hands += HandSplitter.get_hand_count(data)
            except Exception:
                pass
        self.progress.total_hands = total_hands

        for json_path in self.files:
            if self._stop_requested:
                return False

            self.progress.current_file = json_path.name
            success = await self._simulate_file(json_path)

            if not success and self.status == Status.ERROR:
                return False

        if not self._stop_requested:
            self.status = Status.COMPLETED
            self._log(f"Table {self.table_name} completed")
        return True

    async def _simulate_file(self, json_path: Path) -> bool:
        """Simulate single file for this table.

        Handles specific exceptions:
        - json.JSONDecodeError: Invalid JSON format
        - PermissionError: Access denied
        - FileNotFoundError: File removed during processing
        - OSError: Disk/network errors (with specific errno handling)
        """
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            hands = HandSplitter.split_hands(data)
            metadata = HandSplitter.extract_metadata(data)

            if not hands:
                return True

            # Determine output path (preserve structure under table)
            output_path = self.target_path / self.table_name / json_path.name

            for i in range(1, len(hands) + 1):
                if self._stop_requested:
                    return False

                cumulative = HandSplitter.build_cumulative(hands, i, metadata)
                content = json.dumps(cumulative, indent=2, ensure_ascii=False)

                # Write with retry and specific error handling
                write_success = False
                for attempt in range(1, self.settings.retry_count + 1):
                    try:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_text(content, encoding="utf-8")
                        write_success = True
                        break
                    except PermissionError as e:
                        self._log(f"Permission denied: {output_path} - {e}", "ERROR")
                        self.status = Status.ERROR
                        return False
                    except OSError as e:
                        if e.errno == errno.ENOSPC:
                            self._log(f"No disk space left: {output_path}", "ERROR")
                            self.status = Status.ERROR
                            return False
                        elif e.errno == errno.EROFS:
                            self._log(f"Read-only file system: {output_path}", "ERROR")
                            self.status = Status.ERROR
                            return False
                        else:
                            self._log(
                                f"Write attempt {attempt}/{self.settings.retry_count} failed: {e}",
                                "WARNING",
                            )
                            if attempt == self.settings.retry_count:
                                self.status = Status.ERROR
                                return False
                            time.sleep(self.settings.retry_delay_sec)

                if not write_success:
                    return False

                # Thread-safe progress update
                with self._progress_lock:
                    self.progress.current_hand += 1
                self._log(f"Hand {i}/{len(hands)} generated", "SUCCESS")

                if i < len(hands):
                    await asyncio.sleep(self.interval)

            return True

        except json.JSONDecodeError as e:
            self._log(f"JSON parse error in {json_path.name}: {e}", "ERROR")
            return False
        except PermissionError as e:
            self._log(f"Permission denied reading {json_path.name}: {e}", "ERROR")
            return False
        except FileNotFoundError as e:
            self._log(f"File not found: {json_path.name}: {e}", "ERROR")
            return False
        except Exception as e:
            self._log(f"Error processing {json_path.name}: {e}", "ERROR")
            return False


@dataclass
class ParallelSimulationOrchestrator:
    """Orchestrator for parallel multi-table simulation.

    Memory: Logs use deque with maxlen for efficient circular buffer.
    """

    source_path: Path
    target_path: Path
    interval: int = 60
    settings: SimulatorSettings = field(default_factory=get_simulator_settings)

    # State
    status: Status = field(default=Status.IDLE, init=False)
    tasks: dict[str, TableSimulationTask] = field(default_factory=dict, init=False)
    # Use deque for memory-efficient log rotation (O(1))
    logs: deque[LogEntry] = field(
        default_factory=lambda: deque(maxlen=100), init=False
    )
    _stop_requested: bool = field(default=False, init=False)

    def _log(self, message: str, level: str = "INFO") -> None:
        """Add log entry (memory-efficient)."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
        )
        # deque(maxlen=100) auto-rotates (O(1))
        self.logs.append(entry)
        logger.info(str(entry))

    def _group_files_by_table(self, files: list[Path]) -> dict[str, list[Path]]:
        """Group files by table (first directory component)."""
        tables: dict[str, list[Path]] = {}
        for f in files:
            try:
                rel = f.relative_to(self.source_path)
                table = rel.parts[0] if len(rel.parts) > 1 else "default"
            except ValueError:
                table = "default"
            tables.setdefault(table, []).append(f)
        return tables

    def stop(self) -> None:
        """Stop all tasks."""
        self._stop_requested = True
        for task in self.tasks.values():
            task.stop()
        self.status = Status.STOPPED
        self._log("Parallel simulation stopped", "WARNING")

    async def run(self, selected_files: list[Path]) -> None:
        """Run parallel simulation for selected files."""
        self._stop_requested = False
        self.status = Status.RUNNING

        self._log("Starting parallel simulation")
        self._log(f"Source: {self.source_path}")
        self._log(f"Target: {self.target_path}")

        # Group files by table
        grouped = self._group_files_by_table(selected_files)
        self._log(f"Found {len(grouped)} tables: {list(grouped.keys())}")

        # Create tasks for each table
        self.tasks.clear()
        for table_name, files in grouped.items():
            task = TableSimulationTask(
                table_name=table_name,
                files=files,
                target_path=self.target_path,
                interval=self.interval,
                settings=self.settings,
            )
            self.tasks[table_name] = task

        # Run all tasks in parallel
        results = await asyncio.gather(
            *(task.run() for task in self.tasks.values()),
            return_exceptions=True,
        )

        # Check results
        all_success = all(
            isinstance(r, bool) and r for r in results
        )

        if self._stop_requested:
            self.status = Status.STOPPED
        elif all_success:
            self.status = Status.COMPLETED
            self._log("Parallel simulation completed", "SUCCESS")
        else:
            self.status = Status.ERROR
            self._log("Some tasks failed", "ERROR")

    @property
    def aggregate_progress(self) -> SimulationProgress:
        """Get aggregated progress across all tasks."""
        total = sum(t.progress.total_hands for t in self.tasks.values())
        current = sum(t.progress.current_hand for t in self.tasks.values())

        # Find earliest start time
        start_times = [
            t.progress.start_time
            for t in self.tasks.values()
            if t.progress.start_time
        ]
        start_time = min(start_times) if start_times else None

        return SimulationProgress(
            current_hand=current,
            total_hands=total,
            start_time=start_time,
        )

    def get_logs(self, limit: int = 50) -> list[LogEntry]:
        """Get combined logs from all tasks."""
        all_logs: list[LogEntry] = list(self.logs)
        for task in self.tasks.values():
            all_logs.extend(task.logs)
        # Sort by timestamp
        all_logs.sort(key=lambda x: x.timestamp)
        return all_logs[-limit:]


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="GFX JSON Simulator for NAS testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--source",
        type=Path,
        default=Path("gfx_json"),
        help="Source directory containing GFX JSON files (default: gfx_json)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Target directory for output files (NAS path)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between hand generations in seconds (default: 60)",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in CLI mode without Streamlit GUI",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    """Main entry point for CLI."""
    args = parse_args()
    setup_logging(args.verbose)

    if not args.no_gui:
        # Launch Streamlit
        import subprocess
        gui_path = Path(__file__).parent / "gui" / "app.py"
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", str(gui_path),
            "--",
            "--source", str(args.source),
            "--target", str(args.target),
            "--interval", str(args.interval),
        ])
        return 0

    # CLI mode
    if not args.source.exists():
        logger.error(f"Source directory not found: {args.source}")
        return 1

    simulator = GFXJsonSimulator(
        source_path=args.source,
        target_path=args.target,
        interval=args.interval,
    )

    try:
        simulator.run_sync()
        return 0 if simulator.status == Status.COMPLETED else 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        simulator.stop()
        return 130


if __name__ == "__main__":
    sys.exit(main())
