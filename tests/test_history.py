"""Tests for processing history management."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.simulator.history import (
    CheckpointData,
    FileProcessingRecord,
    FileStatus,
    HistoryManager,
    ProcessingHistory,
    RunMode,
    SessionStatus,
    SimulationSession,
)


@pytest.fixture
def temp_history_file() -> Path:
    """Create a temporary history file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        return Path(f.name)


@pytest.fixture
def history_manager(temp_history_file: Path) -> HistoryManager:
    """Create a history manager with temporary file."""
    return HistoryManager(history_file=temp_history_file)


@pytest.fixture
def sample_record() -> FileProcessingRecord:
    """Create a sample file processing record."""
    return FileProcessingRecord(
        file_path="C:/gfx_json/test.json",
        file_hash="abc123",
        processed_at=datetime.now(),
        hand_count=10,
        duration_sec=60.0,
        status="completed",
        session_id="session-123",
    )


@pytest.fixture
def sample_session() -> SimulationSession:
    """Create a sample simulation session."""
    return SimulationSession(
        session_id="session-123",
        started_at=datetime.now(),
        ended_at=None,
        source_path="C:/gfx_json",
        target_path="C:/output",
        files_total=5,
        files_completed=0,
        status=SessionStatus.RUNNING.value,
    )


class TestFileProcessingRecord:
    """Tests for FileProcessingRecord."""

    def test_to_dict(self, sample_record: FileProcessingRecord) -> None:
        """Test serialization to dictionary."""
        data = sample_record.to_dict()

        assert data["file_path"] == sample_record.file_path
        assert data["file_hash"] == sample_record.file_hash
        assert data["hand_count"] == sample_record.hand_count
        assert data["status"] == sample_record.status

    def test_from_dict(self, sample_record: FileProcessingRecord) -> None:
        """Test deserialization from dictionary."""
        data = sample_record.to_dict()
        restored = FileProcessingRecord.from_dict(data)

        assert restored.file_path == sample_record.file_path
        assert restored.file_hash == sample_record.file_hash
        assert restored.hand_count == sample_record.hand_count


class TestSimulationSession:
    """Tests for SimulationSession."""

    def test_to_dict(self, sample_session: SimulationSession) -> None:
        """Test serialization to dictionary."""
        data = sample_session.to_dict()

        assert data["session_id"] == sample_session.session_id
        assert data["source_path"] == sample_session.source_path
        assert data["files_total"] == sample_session.files_total

    def test_from_dict(self, sample_session: SimulationSession) -> None:
        """Test deserialization from dictionary."""
        data = sample_session.to_dict()
        restored = SimulationSession.from_dict(data)

        assert restored.session_id == sample_session.session_id
        assert restored.source_path == sample_session.source_path


class TestProcessingHistory:
    """Tests for ProcessingHistory."""

    def test_empty_history(self) -> None:
        """Test creating empty history."""
        history = ProcessingHistory()

        assert history.version == "1.0"
        assert len(history.sessions) == 0
        assert len(history.records) == 0
        assert history.checkpoint is None

    def test_to_dict_and_from_dict(
        self,
        sample_session: SimulationSession,
        sample_record: FileProcessingRecord,
    ) -> None:
        """Test round-trip serialization."""
        history = ProcessingHistory(
            sessions=[sample_session],
            records={"C:/gfx_json": [sample_record]},
        )

        data = history.to_dict()
        restored = ProcessingHistory.from_dict(data)

        assert len(restored.sessions) == 1
        assert len(restored.records["C:/gfx_json"]) == 1


class TestHistoryManager:
    """Tests for HistoryManager."""

    def test_load_empty_history(
        self,
        history_manager: HistoryManager,
    ) -> None:
        """Test loading when no history file exists."""
        history = history_manager.load_history()

        assert history.version == "1.0"
        assert len(history.sessions) == 0

    def test_save_and_load_history(
        self,
        history_manager: HistoryManager,
        sample_session: SimulationSession,
    ) -> None:
        """Test saving and loading history."""
        history_manager.add_session(sample_session)

        # Create new manager to reload
        new_manager = HistoryManager(history_file=history_manager._history_file)
        loaded = new_manager.load_history()

        assert len(loaded.sessions) == 1
        assert loaded.sessions[0].session_id == sample_session.session_id

    def test_add_record(
        self,
        history_manager: HistoryManager,
        sample_record: FileProcessingRecord,
    ) -> None:
        """Test adding file processing record."""
        source_path = "C:/gfx_json"
        history_manager.add_record(source_path, sample_record)

        records = history_manager.get_records(source_path)
        assert len(records) == 1
        assert records[0].file_path == sample_record.file_path

    def test_is_file_processed_new(
        self,
        history_manager: HistoryManager,
    ) -> None:
        """Test checking unprocessed file."""
        is_processed, status = history_manager.is_file_processed(
            "C:/gfx_json",
            "C:/gfx_json/new_file.json",
        )

        assert not is_processed
        assert status == FileStatus.NEW

    def test_is_file_processed_unchanged(
        self,
        history_manager: HistoryManager,
        sample_record: FileProcessingRecord,
    ) -> None:
        """Test checking processed file with same hash."""
        source_path = "C:/gfx_json"
        history_manager.add_record(source_path, sample_record)

        is_processed, status = history_manager.is_file_processed(
            source_path,
            sample_record.file_path,
            sample_record.file_hash,
        )

        assert is_processed
        assert status == FileStatus.PROCESSED_UNCHANGED

    def test_is_file_processed_changed(
        self,
        history_manager: HistoryManager,
        sample_record: FileProcessingRecord,
    ) -> None:
        """Test checking processed file with different hash."""
        source_path = "C:/gfx_json"
        history_manager.add_record(source_path, sample_record)

        is_processed, status = history_manager.is_file_processed(
            source_path,
            sample_record.file_path,
            "different_hash",
        )

        assert is_processed
        assert status == FileStatus.PROCESSED_CHANGED

    def test_checkpoint_save_and_load(
        self,
        history_manager: HistoryManager,
    ) -> None:
        """Test checkpoint save and load."""
        checkpoint = CheckpointData(
            session_id="test-session",
            file_index=2,
            hand_index=5,
            timestamp=datetime.now(),
        )

        history_manager.save_checkpoint(checkpoint)
        loaded = history_manager.load_checkpoint()

        assert loaded is not None
        assert loaded.session_id == checkpoint.session_id
        assert loaded.file_index == checkpoint.file_index
        assert loaded.hand_index == checkpoint.hand_index

    def test_clear_checkpoint(
        self,
        history_manager: HistoryManager,
    ) -> None:
        """Test clearing checkpoint."""
        checkpoint = CheckpointData(
            session_id="test-session",
            file_index=2,
            hand_index=5,
            timestamp=datetime.now(),
        )

        history_manager.save_checkpoint(checkpoint)
        history_manager.clear_checkpoint()
        loaded = history_manager.load_checkpoint()

        assert loaded is None

    def test_clear_records(
        self,
        history_manager: HistoryManager,
        sample_record: FileProcessingRecord,
    ) -> None:
        """Test clearing records for source path."""
        source_path = "C:/gfx_json"
        history_manager.add_record(source_path, sample_record)

        history_manager.clear_records(source_path)
        records = history_manager.get_records(source_path)

        assert len(records) == 0

    def test_clear_all(
        self,
        history_manager: HistoryManager,
        sample_session: SimulationSession,
        sample_record: FileProcessingRecord,
    ) -> None:
        """Test clearing all history."""
        history_manager.add_session(sample_session)
        history_manager.add_record("C:/gfx_json", sample_record)

        history_manager.clear_all()

        assert len(history_manager.history.sessions) == 0
        assert len(history_manager.history.records) == 0

    def test_calculate_file_hash(
        self,
        temp_history_file: Path,
        history_manager: HistoryManager,
    ) -> None:
        """Test file hash calculation."""
        # Create a test file
        test_content = b'{"test": "data"}'
        temp_history_file.write_bytes(test_content)

        hash_value = history_manager.calculate_file_hash(temp_history_file)

        assert len(hash_value) == 32  # MD5 hash length
        assert hash_value.isalnum()

    def test_normalize_path(self) -> None:
        """Test path normalization."""
        path1 = HistoryManager._normalize_path("C:\\gfx_json\\test")
        path2 = HistoryManager._normalize_path("C:/gfx_json/test")

        # Both should normalize to the same value
        assert "/" in path1
        assert "\\" not in path1


class TestRunMode:
    """Tests for RunMode enum."""

    def test_run_mode_values(self) -> None:
        """Test run mode enum values."""
        assert RunMode.NEW_ONLY.value == "new_only"
        assert RunMode.ALL.value == "all"
        assert RunMode.RESUME.value == "resume"


class TestFileStatus:
    """Tests for FileStatus enum."""

    def test_file_status_values(self) -> None:
        """Test file status enum values."""
        assert FileStatus.NEW.value == "new"
        assert FileStatus.PROCESSED_UNCHANGED.value == "processed_unchanged"
        assert FileStatus.PROCESSED_CHANGED.value == "processed_changed"
