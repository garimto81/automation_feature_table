"""Tests for main application module."""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# Mock cv2 before importing main module
mock_cv2 = MagicMock()
mock_cv2.VideoCapture = MagicMock()
mock_cv2.CAP_PROP_BUFFERSIZE = 38
sys.modules["cv2"] = mock_cv2


# ============================================================================
# Mock Settings Classes
# ============================================================================


@dataclass
class MockPokerGFXSettings:
    """Mock PokerGFX settings."""

    api_url: str = "ws://test.pokergfx.io/api"
    api_key: str = "test-api-key"
    reconnect_interval: float = 1.0
    max_retries: int = 3


@dataclass
class MockGeminiSettings:
    """Mock Gemini settings."""

    api_key: str = "test-gemini-key"
    model: str = "gemini-2.5-flash"
    ws_url: str = "wss://test.gemini.api/ws"
    session_timeout: int = 600
    confidence_threshold: float = 0.80


@dataclass
class MockVideoSettings:
    """Mock Video settings."""

    streams: list = field(default_factory=list)
    fps: int = 1
    jpeg_quality: int = 80
    buffer_size: int = 10


@dataclass
class MockDatabaseSettings:
    """Mock Database settings."""

    host: str = "localhost"
    port: int = 5432
    database: str = "test_db"
    username: str = "test_user"
    password: str = "test_pass"
    pool_size: int = 5


@dataclass
class MockVMixSettings:
    """Mock VMix settings."""

    host: str = "127.0.0.1"
    port: int = 8088
    timeout: float = 5.0
    auto_record: bool = True


@dataclass
class MockRecordingSettings:
    """Mock Recording settings."""

    output_path: str = "./test_recordings"
    format: str = "mp4"
    max_duration_seconds: int = 600
    min_duration_seconds: int = 10


@dataclass
class MockGradingSettings:
    """Mock Grading settings."""

    playtime_threshold: int = 120
    board_combo_threshold: int = 7


@dataclass
class MockFallbackSettings:
    """Mock Fallback settings."""

    enabled: bool = True
    primary_timeout: int = 30
    secondary_timeout: int = 60
    mismatch_threshold: int = 3


@dataclass
class MockSettings:
    """Mock Settings for testing."""

    pokergfx: MockPokerGFXSettings = field(default_factory=MockPokerGFXSettings)
    gemini: MockGeminiSettings = field(default_factory=MockGeminiSettings)
    video: MockVideoSettings = field(default_factory=MockVideoSettings)
    database: MockDatabaseSettings = field(default_factory=MockDatabaseSettings)
    vmix: MockVMixSettings = field(default_factory=MockVMixSettings)
    recording: MockRecordingSettings = field(default_factory=MockRecordingSettings)
    grading: MockGradingSettings = field(default_factory=MockGradingSettings)
    fallback: MockFallbackSettings = field(default_factory=MockFallbackSettings)
    log_level: str = "INFO"
    debug: bool = False
    table_ids: list = field(default_factory=lambda: ["table_1", "table_2"])


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return MockSettings()


# ============================================================================
# PokerHandCaptureSystem Tests
# ============================================================================


class TestPokerHandCaptureSystemImport:
    """Test that PokerHandCaptureSystem can be imported."""

    def test_import(self):
        """Test module import."""
        from src.main import PokerHandCaptureSystem

        assert PokerHandCaptureSystem is not None

    def test_main_import(self):
        """Test main function import."""
        from src.main import main

        assert main is not None


class TestPokerHandCaptureSystemInit:
    """Test PokerHandCaptureSystem initialization."""

    def test_init_with_settings(self, mock_settings):
        """Test initialization with provided settings."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)

                                        assert system.settings == mock_settings
                                        assert system._running is False

    def test_init_creates_components(self, mock_settings):
        """Test that all components are created."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager") as mock_db:
            with patch("src.main.HandRepository") as mock_repo:
                with patch("src.main.PokerGFXClient") as mock_client:
                    with patch("src.main.VideoCapture") as mock_video:
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            with patch("src.main.VMixClient") as mock_vmix:
                                with patch("src.main.HandGrader") as mock_grader:
                                    with patch("src.main.FailureDetector") as mock_fallback:
                                        system = PokerHandCaptureSystem(mock_settings)

                                        mock_client.assert_called_once()
                                        mock_video.assert_called_once()
                                        mock_fusion.assert_called_once()
                                        mock_db.assert_called_once()
                                        mock_vmix.assert_called_once()


class TestPokerHandCaptureSystemStart:
    """Test start method."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self, mock_settings):
        """Test that start sets running flag."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager") as mock_db:
            mock_db.return_value.connect = AsyncMock()
            mock_db.return_value.create_tables = AsyncMock()
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient") as mock_vmix:
                                mock_vmix.return_value.ping = AsyncMock(return_value=True)
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.RecordingManager"):
                                            system = PokerHandCaptureSystem(mock_settings)
                                            await system.start()

                                            assert system._running is True


class TestPokerHandCaptureSystemStop:
    """Test stop method."""

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, mock_settings):
        """Test that stop clears running flag."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager") as mock_db:
            mock_db.return_value.disconnect = AsyncMock()
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient") as mock_client:
                    mock_client.return_value.disconnect = AsyncMock()
                    with patch("src.main.VideoCapture") as mock_video:
                        mock_video.return_value.release_all = MagicMock()
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fusion.return_value.get_aggregate_stats = MagicMock(
                                return_value={}
                            )
                            with patch("src.main.VMixClient") as mock_vmix:
                                mock_vmix.return_value.close = AsyncMock()
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)
                                        system._running = True
                                        system.gemini_processors = {}
                                        system.recording_manager = None

                                        await system.stop()

                                        assert system._running is False

    @pytest.mark.asyncio
    async def test_stop_logs_stats(self, mock_settings):
        """Test that stop logs statistics."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager") as mock_db:
            mock_db.return_value.disconnect = AsyncMock()
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient") as mock_client:
                    mock_client.return_value.disconnect = AsyncMock()
                    with patch("src.main.VideoCapture") as mock_video:
                        mock_video.return_value.release_all = MagicMock()
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fusion.return_value.get_aggregate_stats = MagicMock(
                                return_value={"total": 10}
                            )
                            with patch("src.main.VMixClient") as mock_vmix:
                                mock_vmix.return_value.close = AsyncMock()
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)
                                        system.gemini_processors = {}
                                        system.recording_manager = None

                                        await system.stop()

                                        mock_fusion.return_value.get_aggregate_stats.assert_called_once()


class TestPokerHandCaptureSystemHandlers:
    """Test internal handler methods."""

    @pytest.mark.asyncio
    async def test_handle_primary_result(self, mock_settings):
        """Test handling primary result."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository") as mock_repo:
                mock_repo.return_value.save_hand = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fused = MagicMock()
                            mock_fused.is_premium = False
                            mock_fused.table_id = "table_1"
                            mock_fused.hand_number = 1
                            mock_fused.hand_rank = MagicMock(value=5)
                            mock_fusion.return_value.fuse = MagicMock(return_value=mock_fused)
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader") as mock_grader:
                                    mock_grade_result = MagicMock()
                                    mock_grade_result.broadcast_eligible = False
                                    mock_grade_result.grade = "C"
                                    mock_grader.return_value.grade = MagicMock(return_value=mock_grade_result)
                                    with patch("src.main.FailureDetector") as mock_fallback:
                                        mock_fallback.return_value.update_primary_status = MagicMock()
                                        mock_fallback.return_value.record_fusion_match = MagicMock()
                                        mock_fallback.return_value.record_fusion_mismatch = MagicMock()
                                        system = PokerHandCaptureSystem(mock_settings)
                                        system.recording_manager = None

                                        mock_result = MagicMock()
                                        mock_result.table_id = "table_1"

                                        await system._handle_primary_result(mock_result)

                                        mock_fusion.return_value.fuse.assert_called_once()


class TestPokerHandCaptureSystemProcessFused:
    """Test fused result processing."""

    @pytest.mark.asyncio
    async def test_process_fused_result_saves_to_db(self, mock_settings):
        """Test that fused results are saved to database."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository") as mock_repo:
                mock_repo.return_value.save_hand = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader") as mock_grader:
                                    mock_grade_result = MagicMock()
                                    mock_grade_result.broadcast_eligible = False
                                    mock_grade_result.grade = "C"
                                    mock_grader.return_value.grade = MagicMock(return_value=mock_grade_result)
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)
                                        system.recording_manager = None

                                        mock_result = MagicMock()
                                        mock_result.is_premium = False
                                        mock_result.table_id = "table_1"
                                        mock_result.hand_number = 1
                                        mock_result.hand_rank = MagicMock(value=5)

                                        await system._process_fused_result(mock_result)

                                        mock_repo.return_value.save_hand.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_fused_result_logs_premium(self, mock_settings):
        """Test that premium hands are logged."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository") as mock_repo:
                mock_repo.return_value.save_hand = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader") as mock_grader:
                                    mock_grade_result = MagicMock()
                                    mock_grade_result.broadcast_eligible = True
                                    mock_grade_result.grade = "A"
                                    mock_grader.return_value.grade = MagicMock(return_value=mock_grade_result)
                                    with patch("src.main.FailureDetector"):
                                        with patch("src.main.logger") as mock_logger:
                                            system = PokerHandCaptureSystem(mock_settings)
                                            system.recording_manager = None

                                            mock_result = MagicMock()
                                            mock_result.is_premium = True
                                            mock_result.table_id = "table_1"
                                            mock_result.hand_number = 123
                                            mock_result.rank_name = "Royal Flush"
                                            mock_result.hand_rank = MagicMock(value=1)
                                            mock_result.source.value = "primary"

                                            await system._process_fused_result(mock_result)

                                            mock_logger.info.assert_called()


class TestBufferManagement:
    """Test internal buffer management."""

    def test_secondary_buffer_init_empty(self, mock_settings):
        """Test that secondary buffer starts empty."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)

                                        assert system._primary_buffer == {}
                                        assert system._secondary_buffer == {}

    def test_gemini_processors_init_empty(self, mock_settings):
        """Test that gemini processors dict starts empty."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.DatabaseManager"):
            with patch("src.main.HandRepository"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.VMixClient"):
                                with patch("src.main.HandGrader"):
                                    with patch("src.main.FailureDetector"):
                                        system = PokerHandCaptureSystem(mock_settings)

                                        assert system.gemini_processors == {}
