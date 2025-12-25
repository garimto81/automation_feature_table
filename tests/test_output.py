"""Tests for output modules: clip_marker and overlay."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.hand import FusedHandResult, HandRank, SourceType
from src.output.clip_marker import ClipMarker, ClipMarkerManager


# ============================================================================
# Mock Classes
# ============================================================================


@dataclass
class MockOutputSettings:
    """Mock output settings for testing."""

    overlay_ws_port: int = 8081
    clip_markers_path: str = "./test_output/markers"
    edl_format: str = "cmx3600"


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    with TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def output_settings(temp_output_dir):
    """Create mock output settings with temp directory."""
    return MockOutputSettings(clip_markers_path=temp_output_dir)


@pytest.fixture
def sample_fused_result():
    """Create a sample FusedHandResult."""
    return FusedHandResult(
        table_id="table_1",
        hand_number=12345,
        hand_rank=HandRank.FULL_HOUSE,
        confidence=0.95,
        source=SourceType.PRIMARY,
        primary_result=None,
        secondary_result=None,
        cross_validated=True,
        requires_review=False,
        timestamp=datetime(2025, 1, 15, 14, 30, 0),
    )


# ============================================================================
# ClipMarker Tests
# ============================================================================


class TestClipMarker:
    """Test ClipMarker dataclass."""

    def test_create_marker(self):
        """Test creating a clip marker."""
        start = datetime(2025, 1, 15, 14, 30, 0)
        marker = ClipMarker(
            table_id="table_1",
            hand_number=12345,
            hand_rank="Full House",
            is_premium=True,
            start_time=start,
        )

        assert marker.table_id == "table_1"
        assert marker.hand_number == 12345
        assert marker.hand_rank == "Full House"
        assert marker.is_premium is True
        assert marker.start_time == start
        assert marker.end_time is None

    def test_duration_when_end_set(self):
        """Test duration calculation when end time is set."""
        start = datetime(2025, 1, 15, 14, 30, 0)
        end = datetime(2025, 1, 15, 14, 31, 30)

        marker = ClipMarker(
            table_id="table_1",
            hand_number=1,
            hand_rank="Flush",
            is_premium=False,
            start_time=start,
            end_time=end,
        )

        assert marker.duration == timedelta(seconds=90)

    def test_duration_when_no_end(self):
        """Test duration is None when no end time."""
        marker = ClipMarker(
            table_id="table_1",
            hand_number=1,
            hand_rank="Flush",
            is_premium=False,
            start_time=datetime.now(),
        )

        assert marker.duration is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        start = datetime(2025, 1, 15, 14, 30, 0)
        end = datetime(2025, 1, 15, 14, 31, 30)

        marker = ClipMarker(
            table_id="table_1",
            hand_number=1,
            hand_rank="Flush",
            is_premium=False,
            start_time=start,
            end_time=end,
            notes="Test note",
        )

        data = marker.to_dict()

        assert data["table_id"] == "table_1"
        assert data["hand_number"] == 1
        assert data["hand_rank"] == "Flush"
        assert data["is_premium"] is False
        assert data["start_time"] == start.isoformat()
        assert data["end_time"] == end.isoformat()
        assert data["duration_sec"] == 90.0
        assert data["notes"] == "Test note"


# ============================================================================
# ClipMarkerManager Tests
# ============================================================================


class TestClipMarkerManager:
    """Test ClipMarkerManager class."""

    def test_init_creates_directory(self, output_settings):
        """Test that initialization creates output directory."""
        manager = ClipMarkerManager(output_settings)

        assert Path(output_settings.clip_markers_path).exists()
        assert manager.markers == []

    def test_start_hand(self, output_settings):
        """Test starting a hand marker."""
        manager = ClipMarkerManager(output_settings)
        timestamp = datetime(2025, 1, 15, 14, 30, 0)

        marker = manager.start_hand("table_1", 12345, timestamp)

        assert marker.table_id == "table_1"
        assert marker.hand_number == 12345
        assert marker.start_time == timestamp
        assert marker.hand_rank == "Unknown"
        assert "table_1" in manager._active_hands

    def test_end_hand_with_active(self, output_settings, sample_fused_result):
        """Test ending a hand that was started."""
        manager = ClipMarkerManager(output_settings)
        start_time = datetime(2025, 1, 15, 14, 29, 0)

        # Start the hand
        manager.start_hand("table_1", 12345, start_time)

        # End the hand
        marker = manager.end_hand("table_1", sample_fused_result)

        assert marker is not None
        assert marker.hand_rank == sample_fused_result.rank_name
        assert marker.is_premium is True
        assert marker.start_time == start_time
        assert marker.end_time == sample_fused_result.timestamp
        assert len(manager.markers) == 1
        assert "table_1" not in manager._active_hands

    def test_end_hand_without_start(self, output_settings, sample_fused_result):
        """Test ending a hand that wasn't explicitly started."""
        manager = ClipMarkerManager(output_settings)

        marker = manager.end_hand("table_1", sample_fused_result)

        assert marker is not None
        # Start time should be estimated (30 seconds before end)
        assert marker.start_time == sample_fused_result.timestamp - timedelta(seconds=30)
        assert len(manager.markers) == 1

    def test_add_from_result(self, output_settings, sample_fused_result):
        """Test adding marker directly from result."""
        manager = ClipMarkerManager(output_settings)

        marker = manager.add_from_result(sample_fused_result)

        assert marker.table_id == sample_fused_result.table_id
        assert marker.hand_rank == sample_fused_result.rank_name
        assert marker.is_premium == sample_fused_result.is_premium
        assert "Source:" in marker.notes
        assert len(manager.markers) == 1

    def test_get_premium_markers(self, output_settings):
        """Test filtering premium markers."""
        manager = ClipMarkerManager(output_settings)
        now = datetime.now()

        # Add premium marker
        premium_result = FusedHandResult(
            table_id="table_1",
            hand_number=1,
            hand_rank=HandRank.ROYAL_FLUSH,
            confidence=1.0,
            source=SourceType.PRIMARY,
            primary_result=None,
            secondary_result=None,
            cross_validated=True,
            requires_review=False,
            timestamp=now,
        )
        manager.add_from_result(premium_result)

        # Add non-premium marker
        normal_result = FusedHandResult(
            table_id="table_2",
            hand_number=2,
            hand_rank=HandRank.HIGH_CARD,
            confidence=1.0,
            source=SourceType.PRIMARY,
            primary_result=None,
            secondary_result=None,
            cross_validated=True,
            requires_review=False,
            timestamp=now,
        )
        manager.add_from_result(normal_result)

        premium = manager.get_premium_markers()

        assert len(premium) == 1
        assert premium[0].table_id == "table_1"

    def test_export_json(self, output_settings, sample_fused_result):
        """Test exporting markers to JSON."""
        manager = ClipMarkerManager(output_settings)
        manager.add_from_result(sample_fused_result)

        output_path = manager.export_json("test_markers.json")

        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)

        assert data["total_markers"] == 1
        assert data["premium_markers"] == 1
        assert len(data["markers"]) == 1

    def test_export_edl(self, output_settings, sample_fused_result):
        """Test exporting markers to EDL format."""
        manager = ClipMarkerManager(output_settings)
        manager.add_from_result(sample_fused_result)

        output_path = manager.export_edl("test_markers.edl")

        assert output_path.exists()
        content = output_path.read_text()

        assert "TITLE: Poker Hand Markers" in content
        assert "FCM: NON-DROP FRAME" in content
        assert "Hand #12345" in content
        assert "PREMIUM HAND" in content

    def test_export_fcpxml(self, output_settings, sample_fused_result):
        """Test exporting markers to FCPXML format."""
        manager = ClipMarkerManager(output_settings)
        manager.add_from_result(sample_fused_result)

        output_path = manager.export_fcpxml("test_markers.fcpxml")

        assert output_path.exists()
        content = output_path.read_text()

        assert '<?xml version="1.0"' in content
        assert "fcpxml" in content
        assert "Poker Hand Markers" in content

    def test_clear(self, output_settings, sample_fused_result):
        """Test clearing all markers."""
        manager = ClipMarkerManager(output_settings)
        manager.add_from_result(sample_fused_result)
        manager.start_hand("table_2", 999, datetime.now())

        manager.clear()

        assert len(manager.markers) == 0
        assert len(manager._active_hands) == 0

    def test_datetime_to_timecode(self, output_settings):
        """Test datetime to timecode conversion."""
        manager = ClipMarkerManager(output_settings)

        dt = datetime(2025, 1, 15, 1, 30, 45, 500000)  # 1:30:45.5
        timecode = manager._datetime_to_timecode(dt, fps=30)

        # 500000 us = 0.5 seconds = 14 or 15 frames at 30fps (depending on rounding)
        assert timecode.startswith("01:30:45:")


# ============================================================================
# OverlayServer Tests (simplified due to async WebSocket complexity)
# ============================================================================


class TestOverlayServer:
    """Test OverlayServer class - basic functionality tests."""

    def test_overlay_server_import(self):
        """Test that OverlayServer can be imported."""
        from src.output.overlay import OverlayServer

        assert OverlayServer is not None

    def test_overlay_server_init(self, output_settings):
        """Test OverlayServer initialization."""
        from src.output.overlay import OverlayServer

        server = OverlayServer(output_settings)

        assert server.settings == output_settings
        assert server._clients == set()
        assert server._server is None
        assert server._running is False

    def test_get_client_count_empty(self, output_settings):
        """Test client count when empty."""
        from src.output.overlay import OverlayServer

        server = OverlayServer(output_settings)

        assert server.get_client_count() == 0

    def test_overlay_html_template(self):
        """Test that OVERLAY_HTML template exists."""
        from src.output.overlay import OVERLAY_HTML

        assert "<!DOCTYPE html>" in OVERLAY_HTML
        assert "Poker Hand Overlay" in OVERLAY_HTML
        assert "WebSocket" in OVERLAY_HTML
