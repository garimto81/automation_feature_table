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
class MockOutputSettings:
    """Mock Output settings."""

    overlay_ws_port: int = 8081
    clip_markers_path: str = "./test_output/markers"
    edl_format: str = "cmx3600"


@dataclass
class MockSettings:
    """Mock Settings for testing."""

    pokergfx: MockPokerGFXSettings = field(default_factory=MockPokerGFXSettings)
    gemini: MockGeminiSettings = field(default_factory=MockGeminiSettings)
    video: MockVideoSettings = field(default_factory=MockVideoSettings)
    output: MockOutputSettings = field(default_factory=MockOutputSettings)
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

        with patch("src.main.ClipMarkerManager"):
            with patch("src.main.OverlayServer"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            system = PokerHandCaptureSystem(mock_settings)

                            assert system.settings == mock_settings
                            assert system._running is False

    def test_init_creates_components(self, mock_settings):
        """Test that all components are created."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager") as mock_clip:
            with patch("src.main.OverlayServer") as mock_overlay:
                with patch("src.main.PokerGFXClient") as mock_client:
                    with patch("src.main.VideoCapture") as mock_video:
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            system = PokerHandCaptureSystem(mock_settings)

                            mock_client.assert_called_once()
                            mock_video.assert_called_once()
                            mock_fusion.assert_called_once()
                            mock_overlay.assert_called_once()
                            mock_clip.assert_called_once()


class TestPokerHandCaptureSystemStart:
    """Test start method."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self, mock_settings):
        """Test that start sets running flag."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager"):
            with patch("src.main.OverlayServer") as mock_overlay:
                mock_overlay.return_value.start = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            system = PokerHandCaptureSystem(mock_settings)
                            await system.start()

                            assert system._running is True


class TestPokerHandCaptureSystemStop:
    """Test stop method."""

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, mock_settings):
        """Test that stop clears running flag."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager") as mock_clip:
            mock_clip.return_value.markers = []
            with patch("src.main.OverlayServer") as mock_overlay:
                mock_overlay.return_value.stop = AsyncMock()
                with patch("src.main.PokerGFXClient") as mock_client:
                    mock_client.return_value.disconnect = AsyncMock()
                    with patch("src.main.VideoCapture") as mock_video:
                        mock_video.return_value.release_all = MagicMock()
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fusion.return_value.get_aggregate_stats = MagicMock(
                                return_value={}
                            )
                            system = PokerHandCaptureSystem(mock_settings)
                            system._running = True
                            system.gemini_processors = {}

                            await system.stop()

                            assert system._running is False

    @pytest.mark.asyncio
    async def test_stop_exports_markers(self, mock_settings):
        """Test that stop exports markers if present."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager") as mock_clip:
            mock_marker = MagicMock()
            mock_clip.return_value.markers = [mock_marker]
            mock_clip.return_value.export_json = MagicMock()
            mock_clip.return_value.export_edl = MagicMock()
            with patch("src.main.OverlayServer") as mock_overlay:
                mock_overlay.return_value.stop = AsyncMock()
                with patch("src.main.PokerGFXClient") as mock_client:
                    mock_client.return_value.disconnect = AsyncMock()
                    with patch("src.main.VideoCapture") as mock_video:
                        mock_video.return_value.release_all = MagicMock()
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fusion.return_value.get_aggregate_stats = MagicMock(
                                return_value={}
                            )
                            system = PokerHandCaptureSystem(mock_settings)
                            system.gemini_processors = {}

                            await system.stop()

                            mock_clip.return_value.export_json.assert_called_once()
                            mock_clip.return_value.export_edl.assert_called_once()


class TestPokerHandCaptureSystemHandlers:
    """Test internal handler methods."""

    @pytest.mark.asyncio
    async def test_handle_primary_result(self, mock_settings):
        """Test handling primary result."""
        from src.main import PokerHandCaptureSystem
        from src.models.hand import HandRank, HandResult

        with patch("src.main.ClipMarkerManager") as mock_clip:
            mock_clip.return_value.add_from_result = MagicMock()
            with patch("src.main.OverlayServer") as mock_overlay:
                mock_overlay.return_value.broadcast_hand_result = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine") as mock_fusion:
                            mock_fused = MagicMock()
                            mock_fused.is_premium = False
                            mock_fusion.return_value.fuse = MagicMock(return_value=mock_fused)

                            system = PokerHandCaptureSystem(mock_settings)

                            # Create a mock result
                            mock_result = MagicMock()
                            mock_result.table_id = "table_1"

                            await system._handle_primary_result(mock_result)

                            mock_fusion.return_value.fuse.assert_called_once()
                            mock_overlay.return_value.broadcast_hand_result.assert_called_once()


class TestPokerHandCaptureSystemProcessFused:
    """Test fused result processing."""

    @pytest.mark.asyncio
    async def test_process_fused_result_broadcasts(self, mock_settings):
        """Test that fused results are broadcast."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager") as mock_clip:
            mock_clip.return_value.add_from_result = MagicMock()
            with patch("src.main.OverlayServer") as mock_overlay:
                mock_overlay.return_value.broadcast_hand_result = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            system = PokerHandCaptureSystem(mock_settings)

                            mock_result = MagicMock()
                            mock_result.is_premium = False

                            await system._process_fused_result(mock_result)

                            mock_overlay.return_value.broadcast_hand_result.assert_called_once_with(
                                mock_result
                            )
                            mock_clip.return_value.add_from_result.assert_called_once_with(
                                mock_result
                            )

    @pytest.mark.asyncio
    async def test_process_fused_result_logs_premium(self, mock_settings):
        """Test that premium hands are logged."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager") as mock_clip:
            mock_clip.return_value.add_from_result = MagicMock()
            with patch("src.main.OverlayServer") as mock_overlay:
                mock_overlay.return_value.broadcast_hand_result = AsyncMock()
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            with patch("src.main.logger") as mock_logger:
                                system = PokerHandCaptureSystem(mock_settings)

                                mock_result = MagicMock()
                                mock_result.is_premium = True
                                mock_result.table_id = "table_1"
                                mock_result.hand_number = 123
                                mock_result.rank_name = "Royal Flush"
                                mock_result.source.value = "primary"

                                await system._process_fused_result(mock_result)

                                mock_logger.info.assert_called()


class TestBufferManagement:
    """Test internal buffer management."""

    def test_secondary_buffer_init_empty(self, mock_settings):
        """Test that secondary buffer starts empty."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager"):
            with patch("src.main.OverlayServer"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            system = PokerHandCaptureSystem(mock_settings)

                            assert system._primary_buffer == {}
                            assert system._secondary_buffer == {}

    def test_gemini_processors_init_empty(self, mock_settings):
        """Test that gemini processors dict starts empty."""
        from src.main import PokerHandCaptureSystem

        with patch("src.main.ClipMarkerManager"):
            with patch("src.main.OverlayServer"):
                with patch("src.main.PokerGFXClient"):
                    with patch("src.main.VideoCapture"):
                        with patch("src.main.MultiTableFusionEngine"):
                            system = PokerHandCaptureSystem(mock_settings)

                            assert system.gemini_processors == {}
