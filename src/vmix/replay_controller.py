"""Replay controller for hand-based recording."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.vmix.client import VMixClient

logger = logging.getLogger(__name__)


@dataclass
class HandRecordingResult:
    """Result of a hand recording session."""

    table_id: str
    hand_number: int
    mark_in_time: datetime
    mark_out_time: datetime
    duration_seconds: int
    success: bool
    error_message: str | None = None


class ReplayController:
    """Controls vMix Replay for hand-based recording.

    Manages mark-in/mark-out points and recording lifecycle
    for individual poker hands.
    """

    def __init__(
        self,
        client: VMixClient,
        channel: str = "",
        on_recording_complete: Callable[[HandRecordingResult], None] | None = None,
    ):
        """Initialize replay controller.

        Args:
            client: VMixClient instance
            channel: Replay channel to use (A, B, or empty for default)
            on_recording_complete: Optional callback when recording completes
        """
        self.client = client
        self.channel = channel
        self._on_recording_complete = on_recording_complete

        # Current recording state
        self._current_table_id: str | None = None
        self._current_hand_number: int | None = None
        self._mark_in_time: datetime | None = None
        self._is_recording: bool = False

    @property
    def is_recording(self) -> bool:
        """Check if currently recording a hand."""
        return self._is_recording

    @property
    def current_hand_info(self) -> tuple[str, int] | None:
        """Get current recording info (table_id, hand_number)."""
        if self._is_recording and self._current_table_id and self._current_hand_number:
            return (self._current_table_id, self._current_hand_number)
        return None

    async def start_hand_recording(
        self,
        table_id: str,
        hand_number: int,
        start_main_recording: bool = True,
    ) -> bool:
        """Start recording for a new hand.

        Args:
            table_id: Identifier for the poker table
            hand_number: Hand number being recorded
            start_main_recording: Whether to also start main vMix recording

        Returns:
            True if mark-in was successful
        """
        if self._is_recording:
            logger.warning(
                f"Already recording hand {self._current_table_id} #{self._current_hand_number}. "
                f"Stopping before starting new hand."
            )
            await self.cancel_hand_recording()

        logger.info(f"Starting hand recording: {table_id} #{hand_number}")

        # Mark in point for replay
        success = await self.client.replay_mark_in(self.channel)

        if success:
            self._mark_in_time = datetime.now()
            self._current_table_id = table_id
            self._current_hand_number = hand_number
            self._is_recording = True

            # Optionally start main recording
            if start_main_recording:
                state = await self.client.get_state()
                if state and not state.recording:
                    await self.client.start_recording()

            logger.info(f"Mark-in set for hand {table_id} #{hand_number}")
        else:
            logger.error(f"Failed to set mark-in for hand {table_id} #{hand_number}")

        return success

    async def end_hand_recording(
        self,
        export_event: bool = True,
    ) -> HandRecordingResult | None:
        """End recording for current hand.

        Args:
            export_event: Whether to export the replay event

        Returns:
            HandRecordingResult if successful, None otherwise
        """
        if not self._is_recording:
            logger.warning("No hand recording in progress")
            return None

        table_id = self._current_table_id
        hand_number = self._current_hand_number
        mark_in_time = self._mark_in_time

        logger.info(f"Ending hand recording: {table_id} #{hand_number}")

        # Mark out point
        success = await self.client.replay_mark_out(self.channel)
        mark_out_time = datetime.now()

        if success and mark_in_time:
            duration = int((mark_out_time - mark_in_time).total_seconds())

            result = HandRecordingResult(
                table_id=table_id,
                hand_number=hand_number,
                mark_in_time=mark_in_time,
                mark_out_time=mark_out_time,
                duration_seconds=duration,
                success=True,
            )

            logger.info(
                f"Mark-out set for hand {table_id} #{hand_number}, "
                f"duration: {duration}s"
            )

            # Export replay event if requested
            if export_event:
                export_success = await self.client.replay_export_last_event()
                if not export_success:
                    logger.warning("Failed to export replay event")

            # Call completion callback
            if self._on_recording_complete:
                self._on_recording_complete(result)

            # Reset state
            self._reset_state()

            return result
        else:
            error_msg = "Failed to set mark-out point"
            logger.error(f"{error_msg} for hand {table_id} #{hand_number}")

            result = HandRecordingResult(
                table_id=table_id,
                hand_number=hand_number,
                mark_in_time=mark_in_time,
                mark_out_time=mark_out_time,
                duration_seconds=0,
                success=False,
                error_message=error_msg,
            )

            self._reset_state()
            return result

    async def cancel_hand_recording(self) -> bool:
        """Cancel current hand recording without saving.

        Returns:
            True if cancellation was successful
        """
        if not self._is_recording:
            return True

        logger.info(
            f"Cancelling hand recording: {self._current_table_id} "
            f"#{self._current_hand_number}"
        )

        success = await self.client.replay_mark_cancel()
        self._reset_state()

        return success

    async def create_quick_replay(self, seconds: int = 30) -> bool:
        """Create a quick replay of the last N seconds.

        Args:
            seconds: Number of seconds to capture

        Returns:
            True if successful
        """
        logger.info(f"Creating quick replay ({seconds}s)")
        return await self.client.replay_mark_in_out_live(seconds)

    def _reset_state(self) -> None:
        """Reset internal state."""
        self._current_table_id = None
        self._current_hand_number = None
        self._mark_in_time = None
        self._is_recording = False

    def get_current_duration(self) -> int | None:
        """Get duration of current recording in seconds.

        Returns:
            Duration in seconds, or None if not recording
        """
        if self._is_recording and self._mark_in_time:
            return int((datetime.now() - self._mark_in_time).total_seconds())
        return None
