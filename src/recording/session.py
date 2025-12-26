"""Recording session for individual hands."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RecordingStatus(Enum):
    """Status of a recording session."""

    PENDING = "pending"
    RECORDING = "recording"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RecordingSession:
    """Represents a single hand recording session."""

    table_id: str
    hand_number: int
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    status: RecordingStatus = RecordingStatus.PENDING

    # File info (populated after recording completes)
    file_path: str | None = None
    file_name: str | None = None
    file_size_bytes: int | None = None

    # vMix info
    vmix_input_number: int | None = None
    vmix_recording_id: str | None = None

    # Error tracking
    error_message: str | None = None

    @property
    def duration_seconds(self) -> int | None:
        """Calculate recording duration in seconds."""
        if self.ended_at and self.started_at:
            return int((self.ended_at - self.started_at).total_seconds())
        elif self.status == RecordingStatus.RECORDING:
            return int((datetime.now() - self.started_at).total_seconds())
        return None

    @property
    def is_active(self) -> bool:
        """Check if session is currently recording."""
        return self.status == RecordingStatus.RECORDING

    @property
    def is_completed(self) -> bool:
        """Check if session completed successfully."""
        return self.status == RecordingStatus.COMPLETED

    def start(self) -> None:
        """Mark session as started."""
        self.status = RecordingStatus.RECORDING
        self.started_at = datetime.now()
        logger.debug(f"Recording session started: {self.table_id} #{self.hand_number}")

    def complete(
        self,
        file_path: str,
        file_name: str,
        file_size_bytes: int | None = None,
    ) -> None:
        """Mark session as completed."""
        self.status = RecordingStatus.COMPLETED
        self.ended_at = datetime.now()
        self.file_path = file_path
        self.file_name = file_name
        self.file_size_bytes = file_size_bytes
        logger.info(
            f"Recording session completed: {self.table_id} #{self.hand_number} "
            f"({self.duration_seconds}s)"
        )

    def fail(self, error_message: str) -> None:
        """Mark session as failed."""
        self.status = RecordingStatus.FAILED
        self.ended_at = datetime.now()
        self.error_message = error_message
        logger.error(
            f"Recording session failed: {self.table_id} #{self.hand_number} - "
            f"{error_message}"
        )

    def cancel(self) -> None:
        """Mark session as cancelled."""
        self.status = RecordingStatus.CANCELLED
        self.ended_at = datetime.now()
        logger.info(f"Recording session cancelled: {self.table_id} #{self.hand_number}")

    def to_dict(self) -> dict:
        """Convert session to dictionary."""
        return {
            "table_id": self.table_id,
            "hand_number": self.hand_number,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "vmix_input_number": self.vmix_input_number,
            "error_message": self.error_message,
        }
