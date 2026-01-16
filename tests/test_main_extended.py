"""Extended tests for main application - targeting 70%+ coverage."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import (
    PokerHandCaptureSystem,
    create_primary_source,
)
from src.models.hand import HandRank, HandResult, AIVideoResult


@dataclass
class MockPokerGFXSettings:
    """Mock PokerGFX settings."""

    mode: str = "websocket"
    api_url: str = "ws://test/api"
    api_key: str = "test-key"
    json_watch_path: str = ""
    fallback_enabled: bool = False
    fallback_path: str = ""
    polling_interval: float = 1.0
    processed_db_path: str = "./processed.json"
    file_pattern: str = "*.json"
    file_settle_delay: float = 0.5


@dataclass
class MockSettings:
    """Mock Settings."""

    pokergfx: MockPokerGFXSettings = field(default_factory=MockPokerGFXSettings)
    gemini: MagicMock = field(default_factory=MagicMock)
    video: MagicMock = field(default_factory=MagicMock)
    database: MagicMock = field(default_factory=MagicMock)
    vmix: MagicMock = field(default_factory=MagicMock)
    recording: MagicMock = field(default_factory=MagicMock)
    grading: MagicMock = field(default_factory=MagicMock)
    fallback: MagicMock = field(default_factory=MagicMock)
    log_level: str = "INFO"
    table_ids: list = field(default_factory=lambda: ["table_1", "table_2"])

    def __post_init__(self):
        """Initialize mock objects with required attributes."""
        self.video.streams = ["rtsp://test1", "rtsp://test2"]
        self.video.fps = 1
        self.vmix.auto_record = True
        self.fallback.enabled = True


class TestCreatePrimarySource:
    """Test create_primary_source factory function."""

    def test_create_websocket_source(self):
        """Test creating WebSocket source."""
        settings = MockPokerGFXSettings(mode="websocket")

        with patch("src.main.PokerGFXClient") as mock_client:
            source = create_primary_source(settings)
            mock_client.assert_called_once_with(settings)

    def test_create_json_source_no_fallback(self):
        """Test creating JSON file source without fallback."""
        settings = MockPokerGFXSettings(
            mode="json", json_watch_path="/test/path", fallback_enabled=False
        )

        with patch("src.main.JSONFileWatcher") as mock_watcher:
            source = create_primary_source(settings)
            mock_watcher.assert_called_once_with(settings)

    def test_create_json_source_with_fallback(self):
        """Test creating JSON file source with fallback enabled."""
        settings = MockPokerGFXSettings(
            mode="json",
            json_watch_path="/test/nas",
            fallback_path="/test/local",
            fallback_enabled=True,
        )

        with patch("src.main.FallbackFileWatcher") as mock_fallback:
            source = create_primary_source(settings)
            mock_fallback.assert_called_once()

    def test_create_json_source_no_path(self):
        """Test creating JSON source without path raises error."""
        settings = MockPokerGFXSettings(mode="json", json_watch_path="")

        with pytest.raises(ValueError, match="POKERGFX_JSON_PATH must be set"):
            create_primary_source(settings)

    def test_create_unknown_mode(self):
        """Test creating source with unknown mode raises error."""
        settings = MockPokerGFXSettings(mode="unknown")

        with pytest.raises(ValueError, match="Unknown POKERGFX_MODE"):
            create_primary_source(settings)


class TestPokerHandCaptureSystemStartExtended:
    """Extended tests for start method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    async def test_start_vmix_not_reachable(self, mock_settings):
        """Test start when vMix is not reachable."""
        with patch("src.main.DatabaseManager") as mock_db:
            mock_db.return_value.connect = AsyncMock()
            mock_db.return_value.create_tables = AsyncMock()
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient") as mock_vmix:
                                # vMix ping fails
                                mock_vmix.return_value.ping = AsyncMock(
                                    return_value=False
                                )
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.RecordingManager"):
                                            with patch("src.main.MonitoringService") as mock_monitor:
                                                mock_monitor.return_value.initialize = AsyncMock()
                                                mock_monitor.return_value.log_health = AsyncMock()
                                                mock_monitor.return_value.sync_all_table_statuses = AsyncMock()

                                                system = PokerHandCaptureSystem(
                                                    mock_settings
                                                )
                                                await system.start()

                                                # Should still start, but log warning
                                                assert system._running is True

    async def test_start_initializes_gemini_processors(self, mock_settings):
        """Test that start initializes Gemini processors for each stream."""
        with patch("src.main.DatabaseManager") as mock_db:
            mock_db.return_value.connect = AsyncMock()
            mock_db.return_value.create_tables = AsyncMock()
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture") as mock_video:
                        mock_video.return_value.add_stream = MagicMock()
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient") as mock_vmix:
                                mock_vmix.return_value.ping = AsyncMock(
                                    return_value=True
                                )
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.RecordingManager"):
                                            with patch("src.main.GeminiLiveProcessor") as mock_gemini:
                                                with patch("src.main.MonitoringService") as mock_monitor:
                                                    mock_monitor.return_value.initialize = AsyncMock()
                                                    mock_monitor.return_value.log_health = AsyncMock()
                                                    mock_monitor.return_value.sync_all_table_statuses = AsyncMock()

                                                    system = PokerHandCaptureSystem(
                                                        mock_settings
                                                    )
                                                    await system.start()

                                                    # Should create 2 Gemini processors
                                                    assert mock_gemini.call_count == 2


class TestPokerHandCaptureSystemHandStartExtended:
    """Extended tests for _handle_hand_start method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    async def test_handle_hand_start_updates_monitoring(self, mock_settings):
        """Test that handle_hand_start updates monitoring service."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.MonitoringService") as mock_monitor:
                                            mock_monitor.return_value.update_current_hand = AsyncMock()
                                            mock_monitor.return_value.start_recording_session = AsyncMock()

                                            system = PokerHandCaptureSystem(mock_settings)
                                            system.recording_manager = MagicMock()
                                            system.recording_manager.start_recording = AsyncMock()

                                            await system._handle_hand_start("table_1", 123)

                                            mock_monitor.return_value.update_current_hand.assert_called_once()
                                            mock_monitor.return_value.start_recording_session.assert_called_once()

    async def test_handle_hand_start_no_recording_manager(self, mock_settings):
        """Test handle_hand_start when recording manager is None."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.MonitoringService") as mock_monitor:
                                            mock_monitor.return_value.update_current_hand = AsyncMock()

                                            system = PokerHandCaptureSystem(mock_settings)
                                            system.recording_manager = None

                                            await system._handle_hand_start("table_1", 123)

                                            # Should not raise error
                                            assert "table_1" in system._hand_start_times


class TestPokerHandCaptureSystemHandlePrimaryResultExtended:
    """Extended tests for _handle_primary_result method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    async def test_handle_primary_result_updates_monitoring(
        self, mock_settings
    ):
        """Test that handle_primary_result updates monitoring service."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository") as mock_repo:
                mock_repo.return_value.save_hand = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fused = MagicMock()
                            mock_fused.table_id = "table_1"
                            mock_fused.hand_number = 1
                            mock_fused.hand_rank = MagicMock(value=5)
                            mock_fused.is_premium = False
                            mock_fusion.return_value.fuse = MagicMock(
                                return_value=mock_fused
                            )
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader") as mock_grader:
                                    mock_grade = MagicMock()
                                    mock_grade.broadcast_eligible = False
                                    mock_grade.grade = "C"
                                    mock_grader.return_value.grade = MagicMock(
                                        return_value=mock_grade
                                    )
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.MonitoringService") as mock_monitor:
                                            mock_monitor.return_value.update_table_connection = AsyncMock()
                                            mock_monitor.return_value.update_fusion_result = AsyncMock()

                                            system = PokerHandCaptureSystem(mock_settings)
                                            system.recording_manager = None

                                            mock_result = MagicMock()
                                            mock_result.table_id = "table_1"

                                            await system._handle_primary_result(mock_result)

                                            # Should update monitoring
                                            mock_monitor.return_value.update_table_connection.assert_called_once()


class TestPokerHandCaptureSystemHandleSecondaryResult:
    """Test _handle_secondary_result method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    async def test_handle_secondary_hand_start_event(self, mock_settings):
        """Test handling secondary hand_start event."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.MonitoringService") as mock_monitor:
                                            mock_monitor.return_value.update_table_connection = AsyncMock()

                                            system = PokerHandCaptureSystem(mock_settings)

                                            result = MagicMock()
                                            result.table_id = "table_1"
                                            result.detected_event = "hand_start"
                                            result.timestamp = datetime.now()
                                            result.confidence = 0.9

                                            await system._handle_secondary_result(result)

                                            # Should track start time if not already tracked
                                            assert "table_1" in system._hand_start_times

    async def test_handle_secondary_other_event(self, mock_settings):
        """Test handling secondary event other than hand_start/hand_end."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.MonitoringService") as mock_monitor:
                                            mock_monitor.return_value.update_table_connection = AsyncMock()

                                            system = PokerHandCaptureSystem(mock_settings)

                                            result = MagicMock()
                                            result.table_id = "table_1"
                                            result.detected_event = "flop"
                                            result.confidence = 0.85

                                            await system._handle_secondary_result(result)

                                            # Should store in secondary buffer
                                            assert "table_1" in system._secondary_buffer


class TestPokerHandCaptureSystemRunLoops:
    """Test run loop methods."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    def test_fallback_callbacks_exist(self, mock_settings):
        """Test that fallback callback methods exist."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)

                                        # Check callbacks exist
                                        assert hasattr(system, "_on_fallback_triggered")
                                        assert hasattr(system, "_on_fallback_reset")
                                        assert hasattr(system, "_on_recording_complete")
                                        assert hasattr(system, "_on_manual_hand_completed")


class TestPokerHandCaptureSystemManualMarking:
    """Test manual marking API."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    def test_mark_hand_start_not_in_fallback(self, mock_settings):
        """Test mark_hand_start when not in fallback mode."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector") as mock_detector:
                                        mock_detector.return_value.is_fallback_active = False

                                        system = PokerHandCaptureSystem(mock_settings)

                                        # Should log warning and return early
                                        system.mark_hand_start("table_1")

    def test_mark_hand_end_not_in_fallback(self, mock_settings):
        """Test mark_hand_end when not in fallback mode."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector") as mock_detector:
                                        mock_detector.return_value.is_fallback_active = False

                                        system = PokerHandCaptureSystem(mock_settings)

                                        # Should log warning and return early
                                        system.mark_hand_end("table_1")


class TestPokerHandCaptureSystemGetStats:
    """Test get_system_stats method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        return MockSettings()

    def test_get_stats_with_recording_manager(self, mock_settings):
        """Test get_system_stats with recording manager."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fusion.return_value.get_aggregate_stats = MagicMock(
                                return_value={"total": 10}
                            )
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector") as mock_detector:
                                        mock_detector.return_value.get_stats = MagicMock(
                                            return_value={"fallback_count": 2}
                                        )

                                        system = PokerHandCaptureSystem(mock_settings)
                                        system.recording_manager = MagicMock()
                                        system.recording_manager.get_stats = MagicMock(
                                            return_value={"recordings": 5}
                                        )

                                        stats = system.get_system_stats()

                                        assert "fusion" in stats
                                        assert "recording" in stats
                                        assert stats["recording"]["recordings"] == 5

    def test_get_stats_with_primary_source_stats(self, mock_settings):
        """Test get_system_stats with primary source stats."""
        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient") as mock_client:
                    mock_client.return_value.get_stats = MagicMock(
                        return_value={"reconnects": 2}
                    )
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fusion.return_value.get_aggregate_stats = MagicMock(
                                return_value={"total": 10}
                            )
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector") as mock_detector:
                                        mock_detector.return_value.get_stats = MagicMock(
                                            return_value={"fallback_count": 0}
                                        )

                                        system = PokerHandCaptureSystem(mock_settings)

                                        stats = system.get_system_stats()

                                        assert "fusion" in stats
                                        assert "primary_source" in stats
                                        assert stats["primary_source"]["reconnects"] == 2
