"""Manual marking interface for Plan B fallback."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MarkType(Enum):
    """Types of manual marks."""

    HAND_START = "hand_start"
    HAND_END = "hand_end"
    HIGHLIGHT = "highlight"


@dataclass
class ManualMark:
    """A manual mark entry."""

    table_id: str
    mark_type: MarkType
    marked_at: datetime
    marked_by: str | None = None
    notes: str | None = None
    fallback_reason: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "table_id": self.table_id,
            "mark_type": self.mark_type.value,
            "marked_at": self.marked_at.isoformat(),
            "marked_by": self.marked_by,
            "notes": self.notes,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class PairedMark:
    """A pair of start/end marks representing a hand."""

    start_mark: ManualMark
    end_mark: ManualMark

    @property
    def duration_seconds(self) -> int:
        """Calculate duration between marks."""
        return int(
            (self.end_mark.marked_at - self.start_mark.marked_at).total_seconds()
        )

    @property
    def table_id(self) -> str:
        """Get table ID from start mark."""
        return self.start_mark.table_id


class ManualMarker:
    """Manual marking interface for Plan B fallback.

    Provides simple API for operators to mark hand boundaries
    when automation fails.
    """

    def __init__(
        self,
        table_id: str,
        fallback_reason: str | None = None,
        on_mark_created: Callable[[ManualMark], None] | None = None,
        on_hand_completed: Callable[[PairedMark], None] | None = None,
    ):
        """Initialize manual marker.

        Args:
            table_id: Table identifier
            fallback_reason: Reason for fallback (for context)
            on_mark_created: Callback when a mark is created
            on_hand_completed: Callback when a start/end pair is completed
        """
        self.table_id = table_id
        self.fallback_reason = fallback_reason
        self._on_mark_created = on_mark_created
        self._on_hand_completed = on_hand_completed

        self._marks: list[ManualMark] = []
        self._current_hand_start: ManualMark | None = None
        self._paired_marks: list[PairedMark] = []
        self._hand_counter: int = 0

    def mark_hand_start(
        self,
        operator: str | None = None,
        notes: str | None = None,
    ) -> ManualMark:
        """Mark the start of a new hand.

        Args:
            operator: Name/ID of the operator
            notes: Optional notes

        Returns:
            Created ManualMark
        """
        # If there's an unclosed start, close it first
        if self._current_hand_start:
            logger.warning(
                f"Unclosed hand start at {self._current_hand_start.marked_at}. "
                "Starting new hand."
            )

        mark = ManualMark(
            table_id=self.table_id,
            mark_type=MarkType.HAND_START,
            marked_at=datetime.now(),
            marked_by=operator,
            notes=notes,
            fallback_reason=self.fallback_reason,
        )

        self._marks.append(mark)
        self._current_hand_start = mark
        self._hand_counter += 1

        logger.info(f"Manual HAND_START marked for {self.table_id} (#{self._hand_counter})")

        if self._on_mark_created:
            self._on_mark_created(mark)

        return mark

    def mark_hand_end(
        self,
        operator: str | None = None,
        notes: str | None = None,
    ) -> ManualMark:
        """Mark the end of current hand.

        Args:
            operator: Name/ID of the operator
            notes: Optional notes

        Returns:
            Created ManualMark
        """
        mark = ManualMark(
            table_id=self.table_id,
            mark_type=MarkType.HAND_END,
            marked_at=datetime.now(),
            marked_by=operator,
            notes=notes,
            fallback_reason=self.fallback_reason,
        )

        self._marks.append(mark)

        # Pair with start mark if exists
        if self._current_hand_start:
            duration = (mark.marked_at - self._current_hand_start.marked_at).total_seconds()

            paired = PairedMark(
                start_mark=self._current_hand_start,
                end_mark=mark,
            )
            self._paired_marks.append(paired)

            logger.info(
                f"Manual HAND_END marked for {self.table_id} "
                f"(duration: {duration:.1f}s)"
            )

            if self._on_hand_completed:
                self._on_hand_completed(paired)

            self._current_hand_start = None
        else:
            logger.warning(
                f"Manual HAND_END marked for {self.table_id} (no start mark)"
            )

        if self._on_mark_created:
            self._on_mark_created(mark)

        return mark

    def mark_highlight(
        self,
        operator: str | None = None,
        notes: str | None = None,
    ) -> ManualMark:
        """Mark a highlight moment.

        Args:
            operator: Name/ID of the operator
            notes: Optional notes (e.g., "big pot", "all-in")

        Returns:
            Created ManualMark
        """
        mark = ManualMark(
            table_id=self.table_id,
            mark_type=MarkType.HIGHLIGHT,
            marked_at=datetime.now(),
            marked_by=operator,
            notes=notes,
            fallback_reason=self.fallback_reason,
        )

        self._marks.append(mark)

        logger.info(f"Manual HIGHLIGHT marked for {self.table_id}: {notes}")

        if self._on_mark_created:
            self._on_mark_created(mark)

        return mark

    def cancel_current_hand(self) -> ManualMark | None:
        """Cancel current hand start without end mark.

        Returns:
            The cancelled start mark, or None if no start exists
        """
        if self._current_hand_start:
            cancelled = self._current_hand_start
            self._current_hand_start = None
            logger.info(f"Cancelled current hand for {self.table_id}")
            return cancelled
        return None

    @property
    def is_hand_in_progress(self) -> bool:
        """Check if a hand is currently being marked."""
        return self._current_hand_start is not None

    @property
    def current_hand_duration(self) -> int | None:
        """Get current hand duration in seconds (if in progress)."""
        if self._current_hand_start:
            return int(
                (datetime.now() - self._current_hand_start.marked_at).total_seconds()
            )
        return None

    def get_all_marks(self) -> list[ManualMark]:
        """Get all marks."""
        return self._marks.copy()

    def get_paired_marks(self) -> list[PairedMark]:
        """Get all completed start/end pairs."""
        return self._paired_marks.copy()

    def get_highlights(self) -> list[ManualMark]:
        """Get all highlight marks."""
        return [m for m in self._marks if m.mark_type == MarkType.HIGHLIGHT]

    def get_stats(self) -> dict:
        """Get marking statistics."""
        return {
            "table_id": self.table_id,
            "total_marks": len(self._marks),
            "completed_hands": len(self._paired_marks),
            "highlights": len(self.get_highlights()),
            "hand_in_progress": self.is_hand_in_progress,
            "current_duration": self.current_hand_duration,
            "hand_counter": self._hand_counter,
        }

    def clear(self) -> None:
        """Clear all marks and reset state."""
        self._marks.clear()
        self._paired_marks.clear()
        self._current_hand_start = None
        self._hand_counter = 0
        logger.info(f"Manual marker cleared for {self.table_id}")


class MultiTableManualMarker:
    """Manages manual markers for multiple tables."""

    def __init__(
        self,
        on_mark_created: Callable[[ManualMark], None] | None = None,
        on_hand_completed: Callable[[PairedMark], None] | None = None,
    ):
        self._markers: dict[str, ManualMarker] = {}
        self._on_mark_created = on_mark_created
        self._on_hand_completed = on_hand_completed

    def get_marker(
        self,
        table_id: str,
        fallback_reason: str | None = None,
    ) -> ManualMarker:
        """Get or create marker for a table."""
        if table_id not in self._markers:
            self._markers[table_id] = ManualMarker(
                table_id=table_id,
                fallback_reason=fallback_reason,
                on_mark_created=self._on_mark_created,
                on_hand_completed=self._on_hand_completed,
            )
        return self._markers[table_id]

    def get_all_markers(self) -> dict[str, ManualMarker]:
        """Get all markers."""
        return self._markers.copy()

    def get_all_stats(self) -> dict[str, dict]:
        """Get stats for all tables."""
        return {
            table_id: marker.get_stats()
            for table_id, marker in self._markers.items()
        }
