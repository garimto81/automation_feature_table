"""Tests for MonitoringRepository (PRD-0008)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.models import RecordingSession, SystemHealthLog, TableStatus
from src.database.monitoring_repository import MonitoringRepository


@pytest.fixture
def mock_db_manager():
    """Create a mock DatabaseManager."""
    manager = MagicMock()
    manager.session = MagicMock()
    return manager


@pytest.fixture
def repository(mock_db_manager):
    """Create a MonitoringRepository with mock DB."""
    return MonitoringRepository(mock_db_manager)


class TestTableStatusOperations:
    """Tests for table status operations."""

    async def test_upsert_table_status_creates_new(self, repository, mock_db_manager):
        """Test creating a new table status."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        await repository.upsert_table_status(
            table_id="table_a",
            primary_connected=True,
            secondary_connected=False,
        )

        assert mock_session.add.called

    async def test_upsert_table_status_updates_existing(self, repository, mock_db_manager):
        """Test updating an existing table status."""
        existing_status = TableStatus(
            table_id="table_a",
            primary_connected=False,
            secondary_connected=False,
        )

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: existing_status)
        )
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        await repository.upsert_table_status(
            table_id="table_a",
            primary_connected=True,
        )

        assert existing_status.primary_connected is True


class TestSystemHealthOperations:
    """Tests for system health logging."""

    async def test_log_health_creates_entry(self, repository, mock_db_manager):
        """Test logging a health check."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        await repository.log_health(
            service_name="PostgreSQL",
            status="connected",
            latency_ms=12,
        )

        assert mock_session.add.called
        added_log = mock_session.add.call_args[0][0]
        assert isinstance(added_log, SystemHealthLog)
        assert added_log.service_name == "PostgreSQL"
        assert added_log.status == "connected"
        assert added_log.latency_ms == 12


class TestRecordingSessionOperations:
    """Tests for recording session operations."""

    async def test_create_recording_session(self, repository, mock_db_manager):
        """Test creating a recording session."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        start_time = datetime.utcnow()
        await repository.create_recording_session(
            session_id="session_001",
            table_id="table_a",
            start_time=start_time,
            vmix_input=1,
        )

        assert mock_session.add.called
        added_session = mock_session.add.call_args[0][0]
        assert isinstance(added_session, RecordingSession)
        assert added_session.session_id == "session_001"
        assert added_session.status == "recording"

    async def test_update_recording_session(self, repository, mock_db_manager):
        """Test updating a recording session."""
        existing_session = RecordingSession(
            session_id="session_001",
            table_id="table_a",
            start_time=datetime.utcnow(),
            status="recording",
        )

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: existing_session)
        )
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        end_time = datetime.utcnow()
        await repository.update_recording_session(
            session_id="session_001",
            status="completed",
            end_time=end_time,
            file_size_mb=1024.5,
        )

        assert existing_session.status == "completed"
        assert existing_session.end_time == end_time
        assert existing_session.file_size_mb == 1024.5


class TestDashboardAggregations:
    """Tests for dashboard aggregation queries."""

    async def test_get_today_stats(self, repository, mock_db_manager):
        """Test getting today's statistics."""
        # Mock grade distribution
        with patch.object(
            repository, "get_grade_distribution", new_callable=AsyncMock
        ) as mock_grade:
            mock_grade.return_value = {"A": 5, "B": 10, "C": 20}

            with patch.object(
                repository, "get_broadcast_eligible_count", new_callable=AsyncMock
            ) as mock_broadcast:
                mock_broadcast.return_value = 15

                with patch.object(
                    repository, "get_today_completed_sessions", new_callable=AsyncMock
                ) as mock_sessions:
                    mock_sessions.return_value = [
                        MagicMock(file_size_mb=500),
                        MagicMock(file_size_mb=300),
                    ]

                    stats = await repository.get_today_stats()

                    assert stats["total_hands"] == 35
                    assert stats["grade_distribution"] == {"A": 5, "B": 10, "C": 20}
                    assert stats["broadcast_eligible"] == 15
                    assert stats["broadcast_ratio"] == 42.9
                    assert stats["completed_sessions"] == 2


class TestTableStatusModel:
    """Tests for TableStatus model."""

    def test_table_status_creation(self):
        """Test creating a TableStatus."""
        status = TableStatus(
            table_id="test_table",
            primary_connected=True,
            secondary_connected=False,
        )

        assert status.table_id == "test_table"
        assert status.primary_connected is True
        assert status.secondary_connected is False
        assert status.current_hand_id is None


class TestSystemHealthLogModel:
    """Tests for SystemHealthLog model."""

    def test_health_log_creation(self):
        """Test creating a SystemHealthLog."""
        log = SystemHealthLog(
            service_name="Gemini API",
            status="connected",
            latency_ms=45,
            message="Quota: 85% remaining",
        )

        assert log.service_name == "Gemini API"
        assert log.status == "connected"
        assert log.latency_ms == 45


class TestRecordingSessionModel:
    """Tests for RecordingSession model."""

    def test_recording_session_creation(self):
        """Test creating a RecordingSession."""
        now = datetime.utcnow()
        session = RecordingSession(
            session_id="rec_001",
            table_id="table_a",
            start_time=now,
            status="recording",
        )

        assert session.session_id == "rec_001"
        assert session.table_id == "table_a"
        assert session.status == "recording"

    def test_recording_session_with_file_info(self):
        """Test RecordingSession with file info."""
        session = RecordingSession(
            session_id="rec_002",
            table_id="table_b",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="completed",
            file_size_mb=2048.5,
            file_path="/recordings/session_002.mp4",
        )

        assert session.status == "completed"
        assert session.file_size_mb == 2048.5
        assert session.file_path == "/recordings/session_002.mp4"
