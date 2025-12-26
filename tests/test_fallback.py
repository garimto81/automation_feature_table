"""Tests for fallback/Plan B module."""

from datetime import datetime, timedelta

import pytest

from src.fallback.detector import AutomationState, FailureDetector, FailureReason
from src.fallback.manual_marker import ManualMarker, MarkType, MultiTableManualMarker, PairedMark


class TestFailureDetector:
    """Test cases for FailureDetector."""

    def setup_method(self):
        """Set up test fixtures."""
        self.triggered_reasons = []
        self.reset_called = False

        def on_fallback(reason, state):
            self.triggered_reasons.append(reason)

        def on_reset():
            self.reset_called = True

        self.detector = FailureDetector(
            primary_timeout=30,
            secondary_timeout=60,
            mismatch_threshold=3,
            on_fallback_triggered=on_fallback,
            on_fallback_reset=on_reset,
        )

    def test_initial_state(self):
        """Test initial detector state."""
        assert self.detector.is_fallback_active is False
        assert self.detector.state.primary_connected is False
        assert self.detector.state.secondary_connected is False
        assert self.detector.state.primary_event_count == 0

    def test_update_primary_connected(self):
        """Test updating primary connection status."""
        self.detector.update_primary_status(connected=True, event_received=True)

        assert self.detector.state.primary_connected is True
        assert self.detector.state.primary_event_count == 1
        assert self.detector.state.last_primary_event is not None

    def test_update_secondary_connected(self):
        """Test updating secondary connection status."""
        self.detector.update_secondary_status(connected=True, event_received=True)

        assert self.detector.state.secondary_connected is True
        assert self.detector.state.secondary_event_count == 1

    def test_both_failed_triggers_fallback(self):
        """Test that both sources failing triggers fallback."""
        # First connect both
        self.detector.update_primary_status(connected=True)
        self.detector.update_secondary_status(connected=True)

        # Then disconnect both
        self.detector.update_primary_status(connected=False)
        self.detector.update_secondary_status(connected=False)

        assert self.detector.is_fallback_active is True
        assert FailureReason.BOTH_FAILED in self.triggered_reasons

    def test_fusion_mismatch_triggers_fallback(self):
        """Test that repeated fusion mismatches trigger fallback."""
        # Record 3 mismatches (threshold)
        for _ in range(3):
            self.detector.record_fusion_mismatch()

        assert self.detector.is_fallback_active is True
        assert FailureReason.FUSION_MISMATCH in self.triggered_reasons

    def test_fusion_match_resets_mismatch_count(self):
        """Test that fusion match resets mismatch counter."""
        self.detector.record_fusion_mismatch()
        self.detector.record_fusion_mismatch()
        assert self.detector.state.fusion_mismatch_count == 2

        self.detector.record_fusion_match()
        assert self.detector.state.fusion_mismatch_count == 0

    def test_primary_timeout_detection(self):
        """Test primary timeout detection."""
        self.detector.update_primary_status(connected=True, event_received=True)

        # Simulate old last event
        self.detector._state.last_primary_event = datetime.now() - timedelta(seconds=35)

        reason = self.detector.check_timeouts()
        assert reason == FailureReason.PRIMARY_TIMEOUT

    def test_reset_fallback(self):
        """Test resetting fallback mode."""
        # First connect both sources
        self.detector.update_primary_status(connected=True)
        self.detector.update_secondary_status(connected=True)

        # Then disconnect both to trigger fallback
        self.detector.update_primary_status(connected=False)
        self.detector.update_secondary_status(connected=False)

        assert self.detector.is_fallback_active is True

        # Reset
        self.detector.reset_fallback()

        assert self.detector.is_fallback_active is False
        assert self.reset_called is True

    def test_fallback_not_triggered_twice(self):
        """Test that fallback is not triggered multiple times."""
        # First connect both sources
        self.detector.update_primary_status(connected=True)
        self.detector.update_secondary_status(connected=True)

        # Then disconnect both to trigger fallback
        self.detector.update_primary_status(connected=False)
        self.detector.update_secondary_status(connected=False)

        count = len(self.triggered_reasons)

        # Try to trigger again
        for _ in range(5):
            self.detector.record_fusion_mismatch()

        # Should not have additional triggers
        assert len(self.triggered_reasons) == count

    def test_get_stats(self):
        """Test getting detector statistics."""
        self.detector.update_primary_status(connected=True, event_received=True)

        stats = self.detector.get_stats()

        assert "primary_connected" in stats
        assert "primary_events" in stats
        assert "fallback_active" in stats
        assert stats["primary_connected"] is True
        assert stats["primary_events"] == 1

    def test_automation_state_to_dict(self):
        """Test AutomationState to_dict method."""
        state = AutomationState(
            primary_connected=True,
            secondary_connected=False,
            primary_event_count=5,
        )

        data = state.to_dict()

        assert data["primary_connected"] is True
        assert data["secondary_connected"] is False
        assert data["primary_event_count"] == 5


class TestManualMarker:
    """Test cases for ManualMarker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.created_marks = []
        self.completed_hands = []

        def on_mark(mark):
            self.created_marks.append(mark)

        def on_hand(paired):
            self.completed_hands.append(paired)

        self.marker = ManualMarker(
            table_id="table_1",
            fallback_reason="primary_timeout",
            on_mark_created=on_mark,
            on_hand_completed=on_hand,
        )

    def test_mark_hand_start(self):
        """Test marking hand start."""
        mark = self.marker.mark_hand_start(operator="operator1")

        assert mark.mark_type == MarkType.HAND_START
        assert mark.table_id == "table_1"
        assert mark.marked_by == "operator1"
        assert mark.fallback_reason == "primary_timeout"
        assert self.marker.is_hand_in_progress is True
        assert len(self.created_marks) == 1

    def test_mark_hand_end(self):
        """Test marking hand end."""
        # Start first
        self.marker.mark_hand_start()

        # Then end
        mark = self.marker.mark_hand_end(operator="operator1")

        assert mark.mark_type == MarkType.HAND_END
        assert self.marker.is_hand_in_progress is False
        assert len(self.completed_hands) == 1
        assert isinstance(self.completed_hands[0], PairedMark)

    def test_mark_highlight(self):
        """Test marking highlight."""
        mark = self.marker.mark_highlight(notes="Big pot!")

        assert mark.mark_type == MarkType.HIGHLIGHT
        assert mark.notes == "Big pot!"
        assert len(self.marker.get_highlights()) == 1

    def test_paired_mark_duration(self):
        """Test paired mark duration calculation."""
        import time

        self.marker.mark_hand_start()
        time.sleep(0.1)  # Small delay
        self.marker.mark_hand_end()

        paired = self.completed_hands[0]
        assert paired.duration_seconds >= 0

    def test_cancel_current_hand(self):
        """Test cancelling current hand."""
        self.marker.mark_hand_start()
        assert self.marker.is_hand_in_progress is True

        cancelled = self.marker.cancel_current_hand()

        assert cancelled is not None
        assert self.marker.is_hand_in_progress is False

    def test_current_hand_duration(self):
        """Test getting current hand duration."""
        # No hand in progress
        assert self.marker.current_hand_duration is None

        # Start a hand
        self.marker.mark_hand_start()

        # Should have a duration now
        duration = self.marker.current_hand_duration
        assert duration is not None
        assert duration >= 0

    def test_get_stats(self):
        """Test getting marker statistics."""
        self.marker.mark_hand_start()
        self.marker.mark_hand_end()
        self.marker.mark_highlight()

        stats = self.marker.get_stats()

        assert stats["total_marks"] == 3
        assert stats["completed_hands"] == 1
        assert stats["highlights"] == 1
        assert stats["hand_in_progress"] is False

    def test_clear(self):
        """Test clearing all marks."""
        self.marker.mark_hand_start()
        self.marker.mark_hand_end()

        self.marker.clear()

        assert len(self.marker.get_all_marks()) == 0
        assert len(self.marker.get_paired_marks()) == 0


class TestMultiTableManualMarker:
    """Test cases for MultiTableManualMarker."""

    def setup_method(self):
        """Set up test fixtures."""
        self.multi_marker = MultiTableManualMarker()

    def test_get_marker_creates_new(self):
        """Test that get_marker creates new marker for unknown table."""
        marker = self.multi_marker.get_marker("table_1")

        assert marker is not None
        assert marker.table_id == "table_1"

    def test_get_marker_returns_existing(self):
        """Test that get_marker returns existing marker."""
        marker1 = self.multi_marker.get_marker("table_1")
        marker2 = self.multi_marker.get_marker("table_1")

        assert marker1 is marker2

    def test_get_all_markers(self):
        """Test getting all markers."""
        self.multi_marker.get_marker("table_1")
        self.multi_marker.get_marker("table_2")

        markers = self.multi_marker.get_all_markers()

        assert len(markers) == 2
        assert "table_1" in markers
        assert "table_2" in markers

    def test_get_all_stats(self):
        """Test getting stats for all tables."""
        marker1 = self.multi_marker.get_marker("table_1")
        marker2 = self.multi_marker.get_marker("table_2")

        marker1.mark_hand_start()
        marker2.mark_highlight()

        stats = self.multi_marker.get_all_stats()

        assert "table_1" in stats
        assert "table_2" in stats
        assert stats["table_1"]["hand_in_progress"] is True
        assert stats["table_2"]["highlights"] == 1
