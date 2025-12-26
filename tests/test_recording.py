"""Tests for recording module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.recording.manager import RecordingManager
from src.recording.session import RecordingSession, RecordingStatus
from src.recording.storage import StorageManager


class TestRecordingSession:
    """Test cases for RecordingSession."""

    def test_session_creation(self):
        """Test creating a recording session."""
        session = RecordingSession(
            table_id="table_1",
            hand_number=42,
        )

        assert session.table_id == "table_1"
        assert session.hand_number == 42
        assert session.status == RecordingStatus.PENDING
        assert session.is_active is False

    def test_session_start(self):
        """Test starting a session."""
        session = RecordingSession(table_id="table_1", hand_number=42)
        session.start()

        assert session.status == RecordingStatus.RECORDING
        assert session.is_active is True
        assert session.started_at is not None

    def test_session_complete(self):
        """Test completing a session."""
        session = RecordingSession(table_id="table_1", hand_number=42)
        session.start()
        session.complete(
            file_path="/path/to/file.mp4",
            file_name="file.mp4",
            file_size_bytes=1000000,
        )

        assert session.status == RecordingStatus.COMPLETED
        assert session.is_completed is True
        assert session.is_active is False
        assert session.file_path == "/path/to/file.mp4"
        assert session.ended_at is not None

    def test_session_fail(self):
        """Test failing a session."""
        session = RecordingSession(table_id="table_1", hand_number=42)
        session.start()
        session.fail("Recording error")

        assert session.status == RecordingStatus.FAILED
        assert session.error_message == "Recording error"
        assert session.ended_at is not None

    def test_session_cancel(self):
        """Test cancelling a session."""
        session = RecordingSession(table_id="table_1", hand_number=42)
        session.start()
        session.cancel()

        assert session.status == RecordingStatus.CANCELLED
        assert session.ended_at is not None

    def test_session_duration(self):
        """Test session duration calculation."""
        session = RecordingSession(table_id="table_1", hand_number=42)

        # No duration before start
        assert session.duration_seconds is None

        session.start()
        # Duration while recording
        duration = session.duration_seconds
        assert duration is not None
        assert duration >= 0

        session.complete("/path", "file.mp4")
        # Duration after complete
        assert session.duration_seconds is not None

    def test_session_to_dict(self):
        """Test session to_dict conversion."""
        session = RecordingSession(table_id="table_1", hand_number=42)
        session.start()

        data = session.to_dict()

        assert data["table_id"] == "table_1"
        assert data["hand_number"] == 42
        assert data["status"] == "recording"
        assert "started_at" in data


class TestStorageManager:
    """Test cases for StorageManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = MagicMock()
        self.settings.output_path = "/tmp/test_recordings"
        self.settings.format = "mp4"
        self.storage = StorageManager(self.settings)

    def test_generate_filename(self):
        """Test filename generation."""
        filename = self.storage.generate_filename(
            table_id="table_1",
            hand_number=42,
            timestamp=datetime(2025, 1, 25, 14, 30, 22),
        )

        assert filename == "table_1_hand42_20250125_143022.mp4"

    def test_generate_filename_custom_extension(self):
        """Test filename with custom extension."""
        filename = self.storage.generate_filename(
            table_id="table_1",
            hand_number=42,
            extension="mov",
        )

        assert filename.endswith(".mov")

    def test_get_table_directory(self):
        """Test getting table directory."""
        with patch.object(Path, "mkdir"):
            table_dir = self.storage.get_table_directory("table_1")

            assert str(table_dir).endswith("table_1")

    def test_get_full_path(self):
        """Test getting full file path."""
        with patch.object(Path, "mkdir"):
            path = self.storage.get_full_path(
                table_id="table_1",
                hand_number=42,
            )

            assert "table_1" in str(path)
            assert "hand42" in str(path)
            assert str(path).endswith(".mp4")

    def test_get_file_size(self):
        """Test getting file size."""
        with patch("os.path.getsize", return_value=1000000):
            size = self.storage.get_file_size("/path/to/file.mp4")
            assert size == 1000000

        with patch("os.path.getsize", side_effect=OSError):
            size = self.storage.get_file_size("/nonexistent")
            assert size is None


class TestRecordingManager:
    """Test cases for RecordingManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = MagicMock()
        self.settings.output_path = "/tmp/test_recordings"
        self.settings.format = "mp4"
        self.settings.max_duration_seconds = 600
        self.settings.min_duration_seconds = 10

        self.vmix_client = MagicMock()
        self.completed_sessions = []

        def on_complete(session):
            self.completed_sessions.append(session)

        with patch.object(StorageManager, "ensure_directories"):
            self.manager = RecordingManager(
                settings=self.settings,
                vmix_client=self.vmix_client,
                on_recording_complete=on_complete,
            )

    @pytest.mark.asyncio
    async def test_start_recording(self):
        """Test starting a recording."""
        # Mock replay controller
        controller_mock = AsyncMock()
        controller_mock.start_hand_recording = AsyncMock(return_value=True)
        self.manager._get_controller = MagicMock(return_value=controller_mock)

        session = await self.manager.start_recording("table_1", 42)

        assert session is not None
        assert session.table_id == "table_1"
        assert session.hand_number == 42
        assert session.is_active is True

    @pytest.mark.asyncio
    async def test_stop_recording(self):
        """Test stopping a recording."""
        # Start recording first
        controller_mock = AsyncMock()
        controller_mock.start_hand_recording = AsyncMock(return_value=True)
        controller_mock.end_hand_recording = AsyncMock(
            return_value=MagicMock(
                success=True,
                duration_seconds=60,
            )
        )
        self.manager._get_controller = MagicMock(return_value=controller_mock)

        with patch.object(self.manager.storage, "get_full_path") as mock_path:
            mock_path.return_value = Path("/tmp/file.mp4")

            await self.manager.start_recording("table_1", 42)
            session = await self.manager.stop_recording("table_1")

        assert session is not None
        assert session.is_completed is True
        assert len(self.completed_sessions) == 1

    @pytest.mark.asyncio
    async def test_stop_recording_no_active(self):
        """Test stopping when no active recording."""
        session = await self.manager.stop_recording("table_1")
        assert session is None

    @pytest.mark.asyncio
    async def test_cancel_recording(self):
        """Test cancelling a recording."""
        controller_mock = AsyncMock()
        controller_mock.start_hand_recording = AsyncMock(return_value=True)
        controller_mock.cancel_hand_recording = AsyncMock(return_value=True)
        self.manager._get_controller = MagicMock(return_value=controller_mock)

        await self.manager.start_recording("table_1", 42)
        session = await self.manager.cancel_recording("table_1")

        assert session is not None
        assert session.status == RecordingStatus.CANCELLED

    def test_get_active_session(self):
        """Test getting active session."""
        # No active session
        assert self.manager.get_active_session("table_1") is None

    def test_get_stats(self):
        """Test getting manager statistics."""
        stats = self.manager.get_stats()

        assert "active_recordings" in stats
        assert "total_completed" in stats
        assert "total_failed" in stats
        assert "storage" in stats

    @pytest.mark.asyncio
    async def test_stop_all(self):
        """Test stopping all recordings."""
        controller_mock = AsyncMock()
        controller_mock.start_hand_recording = AsyncMock(return_value=True)
        controller_mock.end_hand_recording = AsyncMock(
            return_value=MagicMock(success=True)
        )
        self.manager._get_controller = MagicMock(return_value=controller_mock)

        with patch.object(self.manager.storage, "get_full_path") as mock_path:
            mock_path.return_value = Path("/tmp/file.mp4")

            await self.manager.start_recording("table_1", 1)
            await self.manager.start_recording("table_2", 2)

            stopped = await self.manager.stop_all()

        assert len(stopped) == 2

    def test_session_history(self):
        """Test session history management."""
        # Add some sessions to history
        for i in range(5):
            session = RecordingSession(table_id="table_1", hand_number=i)
            session.complete(f"/path/{i}.mp4", f"{i}.mp4")
            self.manager._completed_sessions.append(session)

        history = self.manager.get_session_history(limit=3)

        assert len(history) == 3
        # Should be newest first
        assert history[0].hand_number == 4

    def test_session_history_filter_by_table(self):
        """Test filtering session history by table."""
        # Add sessions for different tables
        for i in range(3):
            session = RecordingSession(table_id="table_1", hand_number=i)
            session.complete(f"/path/{i}.mp4", f"{i}.mp4")
            self.manager._completed_sessions.append(session)

        for i in range(2):
            session = RecordingSession(table_id="table_2", hand_number=i)
            session.complete(f"/path/{i}.mp4", f"{i}.mp4")
            self.manager._completed_sessions.append(session)

        history = self.manager.get_session_history(table_id="table_1")

        assert len(history) == 3
        assert all(s.table_id == "table_1" for s in history)
