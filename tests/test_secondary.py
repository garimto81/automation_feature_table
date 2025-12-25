"""Tests for secondary modules: gemini_live and video_capture."""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# Mock cv2 before importing modules that depend on it
mock_cv2 = MagicMock()
mock_cv2.VideoCapture = MagicMock()
mock_cv2.CAP_PROP_BUFFERSIZE = 38
mock_cv2.CAP_PROP_FRAME_WIDTH = 3
mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
mock_cv2.CAP_PROP_FPS = 5
mock_cv2.IMWRITE_JPEG_QUALITY = 1
mock_cv2.imencode = MagicMock(return_value=(True, np.array([0xFF, 0xD8, 0xFF, 0xE0], dtype=np.uint8)))
sys.modules["cv2"] = mock_cv2

from src.models.hand import AIVideoResult, Card, HandRank
from src.secondary.video_capture import VideoCapture, VideoFrame


# ============================================================================
# Mock Classes
# ============================================================================


@dataclass
class MockVideoSettings:
    """Mock video settings for testing."""

    streams: list = None
    fps: int = 1
    jpeg_quality: int = 80
    buffer_size: int = 10

    def __post_init__(self):
        if self.streams is None:
            self.streams = []


@dataclass
class MockGeminiSettings:
    """Mock Gemini settings for testing."""

    api_key: str = "test-api-key"
    model: str = "gemini-2.5-flash"
    ws_url: str = "wss://test.gemini.api/ws"
    session_timeout: int = 600
    confidence_threshold: float = 0.80


@pytest.fixture
def video_settings():
    """Create mock video settings."""
    return MockVideoSettings()


@pytest.fixture
def gemini_settings():
    """Create mock gemini settings."""
    return MockGeminiSettings()


# ============================================================================
# VideoFrame Tests
# ============================================================================


class TestVideoFrame:
    """Test VideoFrame dataclass."""

    def test_create_frame(self):
        """Test creating a video frame."""
        frame_data = np.zeros((1080, 1920, 3), dtype=np.uint8)
        timestamp = datetime.now()

        frame = VideoFrame(
            table_id="table_1",
            frame=frame_data,
            timestamp=timestamp,
            frame_number=42,
        )

        assert frame.table_id == "table_1"
        assert frame.frame.shape == (1080, 1920, 3)
        assert frame.timestamp == timestamp
        assert frame.frame_number == 42

    def test_to_jpeg(self):
        """Test JPEG encoding."""
        # Create a simple test frame (100x100 red image)
        frame_data = np.zeros((100, 100, 3), dtype=np.uint8)
        frame_data[:, :, 2] = 255  # Red channel (BGR format)

        frame = VideoFrame(
            table_id="table_1",
            frame=frame_data,
            timestamp=datetime.now(),
            frame_number=1,
        )

        # Mock imencode to return proper JPEG bytes
        mock_cv2.imencode.return_value = (True, np.array([0xFF, 0xD8, 0xFF, 0xE0], dtype=np.uint8))

        jpeg_bytes = frame.to_jpeg(quality=80)

        assert isinstance(jpeg_bytes, bytes)
        assert len(jpeg_bytes) > 0


# ============================================================================
# VideoCapture Tests
# ============================================================================


class TestVideoCapture:
    """Test VideoCapture class."""

    def test_init(self, video_settings):
        """Test VideoCapture initialization."""
        capture = VideoCapture(video_settings)

        assert capture.settings == video_settings
        assert capture._captures == {}
        assert capture._running is False
        assert capture._frame_counts == {}
        assert capture._buffers == {}

    def test_add_stream_mock(self, video_settings):
        """Test adding a stream with mocked OpenCV."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        with patch("cv2.VideoCapture", return_value=mock_cap):
            result = capture.add_stream("table_1", "rtsp://test/stream")

            assert result is True
            assert "table_1" in capture._captures
            assert "table_1" in capture._frame_counts
            assert "table_1" in capture._buffers

    def test_add_stream_failure(self, video_settings):
        """Test adding a stream that fails to open."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False

        with patch("cv2.VideoCapture", return_value=mock_cap):
            result = capture.add_stream("table_1", "rtsp://invalid/stream")

            assert result is False
            assert "table_1" not in capture._captures

    def test_remove_stream(self, video_settings):
        """Test removing a stream."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream")
            capture.remove_stream("table_1")

            mock_cap.release.assert_called_once()
            assert "table_1" not in capture._captures

    def test_capture_frame(self, video_settings):
        """Test capturing a single frame."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((1080, 1920, 3), dtype=np.uint8))

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream")
            frame = capture.capture_frame("table_1")

            assert frame is not None
            assert frame.table_id == "table_1"
            assert frame.frame_number == 1

    def test_capture_frame_no_stream(self, video_settings):
        """Test capturing from non-existent stream."""
        capture = VideoCapture(video_settings)

        frame = capture.capture_frame("nonexistent")

        assert frame is None

    def test_capture_frame_read_failure(self, video_settings):
        """Test capture when read fails."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream")
            frame = capture.capture_frame("table_1")

            assert frame is None

    def test_stop(self, video_settings):
        """Test stopping capture."""
        capture = VideoCapture(video_settings)
        capture._running = True

        capture.stop()

        assert capture._running is False

    def test_release_all(self, video_settings):
        """Test releasing all captures."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream1")
            capture.add_stream("table_2", "rtsp://test/stream2")

            capture.release_all()

            assert len(capture._captures) == 0
            assert capture._running is False

    def test_get_latest_frame(self, video_settings):
        """Test getting latest frame from buffer."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((100, 100, 3), dtype=np.uint8))

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream")

            # Capture a frame to add to buffer
            capture.capture_frame("table_1")

            latest = capture.get_latest_frame("table_1")

            assert latest is not None
            assert latest.table_id == "table_1"

    def test_get_latest_frame_no_buffer(self, video_settings):
        """Test getting latest frame when no frames captured."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream")

            latest = capture.get_latest_frame("table_1")

            assert latest is None

    def test_get_stream_info(self, video_settings):
        """Test getting stream information."""
        capture = VideoCapture(video_settings)

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda x: {
            3: 1920,  # CAP_PROP_FRAME_WIDTH
            4: 1080,  # CAP_PROP_FRAME_HEIGHT
            5: 30.0,  # CAP_PROP_FPS
        }.get(x, 0)

        with patch("cv2.VideoCapture", return_value=mock_cap):
            capture.add_stream("table_1", "rtsp://test/stream")

            info = capture.get_stream_info("table_1")

            assert info is not None
            assert info["table_id"] == "table_1"
            assert info["width"] == 1920
            assert info["height"] == 1080
            assert info["fps"] == 30.0

    def test_get_stream_info_no_stream(self, video_settings):
        """Test getting info for non-existent stream."""
        capture = VideoCapture(video_settings)

        info = capture.get_stream_info("nonexistent")

        assert info is None


# ============================================================================
# GeminiLiveProcessor Tests
# ============================================================================


class TestGeminiLiveProcessor:
    """Test GeminiLiveProcessor class - basic functionality tests."""

    def test_import(self):
        """Test that GeminiLiveProcessor can be imported."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        assert GeminiLiveProcessor is not None

    def test_init(self, gemini_settings):
        """Test GeminiLiveProcessor initialization."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")

        assert processor.settings == gemini_settings
        assert processor.table_id == "table_1"
        assert processor._ws is None
        assert processor._running is False

    def test_system_prompt_exists(self, gemini_settings):
        """Test that system prompt is defined."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")

        assert processor.SYSTEM_PROMPT is not None
        assert "poker" in processor.SYSTEM_PROMPT.lower()
        assert "JSON" in processor.SYSTEM_PROMPT

    def test_stop(self, gemini_settings):
        """Test stopping processor."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")
        processor._running = True

        processor.stop()

        assert processor._running is False

    def test_should_reconnect_no_session(self, gemini_settings):
        """Test reconnect check when no session started."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")

        assert processor._should_reconnect() is True

    def test_should_reconnect_with_session(self, gemini_settings):
        """Test reconnect check with active session."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")
        processor._session_start = datetime.now()

        assert processor._should_reconnect() is False

    def test_parse_response_valid_json(self, gemini_settings):
        """Test parsing a valid Gemini response."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")

        response = json.dumps({
            "serverContent": {
                "modelTurn": {
                    "parts": [{
                        "text": json.dumps({
                            "event": "hand_end",
                            "cards_detected": ["Ah", "Kd"],
                            "hand_rank": "Full House",
                            "confidence": 0.95,
                            "context": "Player reveals cards"
                        })
                    }]
                }
            }
        })

        result = processor._parse_response(response, datetime.now())

        assert result is not None
        assert result.detected_event == "hand_end"
        assert result.confidence == 0.95
        assert result.hand_rank == HandRank.FULL_HOUSE

    def test_parse_response_invalid_json(self, gemini_settings):
        """Test parsing an invalid response."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")

        result = processor._parse_response("invalid json", datetime.now())

        assert result is None

    def test_parse_response_low_confidence_none_event(self, gemini_settings):
        """Test that low confidence 'none' events are skipped."""
        from src.secondary.gemini_live import GeminiLiveProcessor

        processor = GeminiLiveProcessor(gemini_settings, "table_1")

        response = json.dumps({
            "serverContent": {
                "modelTurn": {
                    "parts": [{
                        "text": json.dumps({
                            "event": "none",
                            "confidence": 0.3,
                            "context": "Nothing detected"
                        })
                    }]
                }
            }
        })

        result = processor._parse_response(response, datetime.now())

        assert result is None


# ============================================================================
# AIVideoResult Tests
# ============================================================================


class TestAIVideoResult:
    """Test AIVideoResult dataclass."""

    def test_create_result(self):
        """Test creating an AI video result."""
        result = AIVideoResult(
            table_id="table_1",
            detected_event="showdown",
            detected_cards=[Card(rank="A", suit="h"), Card(rank="K", suit="d")],
            hand_rank=HandRank.FULL_HOUSE,
            confidence=0.95,
            context="Player A shows full house",
            timestamp=datetime.now(),
        )

        assert result.table_id == "table_1"
        assert result.detected_event == "showdown"
        assert len(result.detected_cards) == 2
        assert result.hand_rank == HandRank.FULL_HOUSE
        assert result.confidence == 0.95

    def test_create_result_minimal(self):
        """Test creating AI video result with minimal data."""
        result = AIVideoResult(
            table_id="table_1",
            detected_event="hand_start",
            detected_cards=[],
            hand_rank=None,
            confidence=0.7,
            context="",
            timestamp=datetime.now(),
        )

        assert result.table_id == "table_1"
        assert result.hand_rank is None
        assert len(result.detected_cards) == 0
