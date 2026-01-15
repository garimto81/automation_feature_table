"""Processing history management for GFX JSON Simulator.

Tracks which files have been processed, enables duplicate detection,
and supports session persistence across restarts.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 이력 파일 경로 (프로젝트 루트)
HISTORY_FILE = Path(__file__).parents[2] / ".simulator_history.json"
HISTORY_VERSION = "1.0"


class FileStatus(Enum):
    """File processing status."""

    NEW = "new"  # 새 파일 (이력 없음)
    PROCESSED_UNCHANGED = "processed_unchanged"  # 처리됨, 해시 일치
    PROCESSED_CHANGED = "processed_changed"  # 처리됨, 해시 불일치 (재처리 권장)


class SessionStatus(Enum):
    """Simulation session status."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class RunMode(Enum):
    """Simulation run mode."""

    NEW_ONLY = "new_only"  # 새 파일만 처리
    ALL = "all"  # 전체 재실행
    RESUME = "resume"  # 이어서 실행 (checkpoint부터)


@dataclass
class FileProcessingRecord:
    """Single file processing record."""

    file_path: str  # 절대 경로
    file_hash: str  # MD5 해시
    processed_at: datetime
    hand_count: int
    duration_sec: float
    status: str  # completed, partial, failed
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "processed_at": self.processed_at.isoformat(),
            "hand_count": self.hand_count,
            "duration_sec": self.duration_sec,
            "status": self.status,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileProcessingRecord:
        """Create from dictionary."""
        return cls(
            file_path=data["file_path"],
            file_hash=data["file_hash"],
            processed_at=datetime.fromisoformat(data["processed_at"]),
            hand_count=data["hand_count"],
            duration_sec=data["duration_sec"],
            status=data["status"],
            session_id=data["session_id"],
        )


@dataclass
class SimulationSession:
    """Simulation session information."""

    session_id: str
    started_at: datetime
    ended_at: datetime | None
    source_path: str
    target_path: str
    files_total: int
    files_completed: int
    status: str  # running, paused, completed, stopped, error

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "files_total": self.files_total,
            "files_completed": self.files_completed,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationSession:
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=(
                datetime.fromisoformat(data["ended_at"])
                if data.get("ended_at")
                else None
            ),
            source_path=data["source_path"],
            target_path=data["target_path"],
            files_total=data["files_total"],
            files_completed=data["files_completed"],
            status=data["status"],
        )


@dataclass
class CheckpointData:
    """Checkpoint data for pause/resume."""

    session_id: str
    file_index: int
    hand_index: int
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "file_index": self.file_index,
            "hand_index": self.hand_index,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointData:
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            file_index=data["file_index"],
            hand_index=data["hand_index"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class ProcessingHistory:
    """Processing history container."""

    version: str = HISTORY_VERSION
    sessions: list[SimulationSession] = field(default_factory=list)
    records: dict[str, list[FileProcessingRecord]] = field(default_factory=dict)
    checkpoint: CheckpointData | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        records_dict: dict[str, list[dict[str, Any]]] = {}
        for source_path, record_list in self.records.items():
            records_dict[source_path] = [r.to_dict() for r in record_list]

        return {
            "version": self.version,
            "sessions": [s.to_dict() for s in self.sessions],
            "records": records_dict,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessingHistory:
        """Create from dictionary."""
        sessions = [
            SimulationSession.from_dict(s) for s in data.get("sessions", [])
        ]

        records: dict[str, list[FileProcessingRecord]] = {}
        for source_path, record_list in data.get("records", {}).items():
            records[source_path] = [
                FileProcessingRecord.from_dict(r) for r in record_list
            ]

        checkpoint = None
        if data.get("checkpoint"):
            checkpoint = CheckpointData.from_dict(data["checkpoint"])

        return cls(
            version=data.get("version", HISTORY_VERSION),
            sessions=sessions,
            records=records,
            checkpoint=checkpoint,
        )


class HistoryManager:
    """Manager for processing history."""

    def __init__(self, history_file: Path | None = None) -> None:
        """Initialize history manager.

        Args:
            history_file: Path to history file. Defaults to project root.
        """
        self._history_file = history_file or HISTORY_FILE
        self._history: ProcessingHistory | None = None
        self._last_save_time: float = 0
        self._save_debounce_sec: float = 5.0

    @property
    def history(self) -> ProcessingHistory:
        """Get or load history."""
        if self._history is None:
            self._history = self.load_history()
        return self._history

    def load_history(self) -> ProcessingHistory:
        """Load history from file.

        Returns:
            ProcessingHistory object (empty if file doesn't exist).
        """
        if not self._history_file.exists():
            logger.debug(f"History file not found: {self._history_file}")
            return ProcessingHistory()

        try:
            data = json.loads(self._history_file.read_text(encoding="utf-8"))
            history = ProcessingHistory.from_dict(data)
            logger.info(
                f"Loaded history: {len(history.sessions)} sessions, "
                f"{sum(len(r) for r in history.records.values())} records"
            )
            return history
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load history: {e}")
            return ProcessingHistory()

    def save_history(self) -> bool:
        """Save history to file.

        Returns:
            True if saved successfully.
        """
        try:
            # 원자적 쓰기: 임시 파일에 쓴 후 rename
            temp_file = self._history_file.with_suffix(".tmp")
            content = json.dumps(
                self.history.to_dict(),
                indent=2,
                ensure_ascii=False,
            )
            temp_file.write_text(content, encoding="utf-8")
            temp_file.replace(self._history_file)
            logger.debug(f"Saved history to {self._history_file}")
            return True
        except OSError as e:
            logger.error(f"Failed to save history: {e}")
            return False

    def add_session(self, session: SimulationSession) -> None:
        """Add or update session.

        Args:
            session: Session to add or update.
        """
        # 기존 세션 업데이트 또는 추가
        for i, s in enumerate(self.history.sessions):
            if s.session_id == session.session_id:
                self.history.sessions[i] = session
                self.save_history()
                return
        self.history.sessions.append(session)
        # 최근 50개 세션만 유지
        if len(self.history.sessions) > 50:
            self.history.sessions = self.history.sessions[-50:]
        self.save_history()

    def add_record(
        self,
        source_path: str,
        record: FileProcessingRecord,
    ) -> None:
        """Add file processing record.

        Args:
            source_path: Normalized source path as key.
            record: Record to add.
        """
        normalized_path = self._normalize_path(source_path)
        if normalized_path not in self.history.records:
            self.history.records[normalized_path] = []

        # 기존 레코드 업데이트 (같은 파일)
        records = self.history.records[normalized_path]
        for i, r in enumerate(records):
            if r.file_path == record.file_path:
                records[i] = record
                self.save_history()
                return

        records.append(record)
        # 소스별 최근 500개 레코드만 유지
        if len(records) > 500:
            self.history.records[normalized_path] = records[-500:]
        self.save_history()

    def get_records(self, source_path: str) -> list[FileProcessingRecord]:
        """Get records for source path.

        Args:
            source_path: Source path to query.

        Returns:
            List of processing records.
        """
        normalized_path = self._normalize_path(source_path)
        return self.history.records.get(normalized_path, [])

    def is_file_processed(
        self,
        source_path: str,
        file_path: str,
        file_hash: str | None = None,
    ) -> tuple[bool, FileStatus]:
        """Check if file has been processed.

        Args:
            source_path: Source directory path.
            file_path: Full path to the file.
            file_hash: Optional MD5 hash of file content.

        Returns:
            Tuple of (is_processed, status).
        """
        records = self.get_records(source_path)

        for record in records:
            if record.file_path == file_path and record.status == "completed":
                if file_hash is None:
                    return True, FileStatus.PROCESSED_UNCHANGED

                if record.file_hash == file_hash:
                    return True, FileStatus.PROCESSED_UNCHANGED
                else:
                    return True, FileStatus.PROCESSED_CHANGED

        return False, FileStatus.NEW

    def get_file_status(
        self,
        source_path: str,
        file_path: Path,
    ) -> tuple[FileStatus, FileProcessingRecord | None]:
        """Get detailed file status with record.

        Args:
            source_path: Source directory path.
            file_path: Path to the file.

        Returns:
            Tuple of (status, record or None).
        """
        file_hash = self.calculate_file_hash(file_path)
        records = self.get_records(source_path)

        for record in records:
            if record.file_path == str(file_path) and record.status == "completed":
                if record.file_hash == file_hash:
                    return FileStatus.PROCESSED_UNCHANGED, record
                else:
                    return FileStatus.PROCESSED_CHANGED, record

        return FileStatus.NEW, None

    def save_checkpoint(self, checkpoint: CheckpointData) -> None:
        """Save checkpoint for resume.

        Args:
            checkpoint: Checkpoint data to save.
        """
        self.history.checkpoint = checkpoint
        self.save_history()

    def load_checkpoint(self) -> CheckpointData | None:
        """Load saved checkpoint.

        Returns:
            CheckpointData or None if not exists.
        """
        return self.history.checkpoint

    def clear_checkpoint(self) -> None:
        """Clear saved checkpoint."""
        self.history.checkpoint = None
        self.save_history()

    def clear_records(self, source_path: str) -> None:
        """Clear records for specific source path.

        Args:
            source_path: Source path to clear.
        """
        normalized_path = self._normalize_path(source_path)
        if normalized_path in self.history.records:
            del self.history.records[normalized_path]
            self.save_history()
            logger.info(f"Cleared history for: {source_path}")

    def clear_all(self) -> None:
        """Clear all history data."""
        self._history = ProcessingHistory()
        self.save_history()
        logger.info("Cleared all history")

    @staticmethod
    def calculate_file_hash(file_path: Path) -> str:
        """Calculate MD5 hash of file content.

        Args:
            file_path: Path to file.

        Returns:
            MD5 hash as hex string.
        """
        try:
            content = file_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except OSError as e:
            logger.warning(f"Failed to calculate hash for {file_path}: {e}")
            return ""

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize path for consistent key usage.

        Args:
            path: Path to normalize.

        Returns:
            Normalized path string.
        """
        return str(Path(path).resolve()).replace("\\", "/")


# 싱글톤 인스턴스
_history_manager: HistoryManager | None = None


def get_history_manager() -> HistoryManager:
    """Get singleton history manager instance."""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager
