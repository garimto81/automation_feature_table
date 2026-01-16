"""Replay controller for hand-based recording.

Timecode Support (PRD-0009 P2 Enhancement):
------------------------------------------
This module supports SMPTE timecode tracking for frame-accurate synchronization
between hand markers and video recordings.

SMPTE Timecode Format: HH:MM:SS:FF (or HH:MM:SS;FF for drop-frame)
- HH: Hours (00-23)
- MM: Minutes (00-59)
- SS: Seconds (00-59)
- FF: Frames (00-29 for 30fps, 00-23 for 24fps)

Example:
```python
# Get current timecode from vMix
timecode = await controller.get_current_timecode()
# Returns: "01:23:45:12" (1 hour, 23 min, 45 sec, frame 12)

# Start recording with timecode tracking
await controller.start_hand_recording(
    table_id="table1",
    hand_number=42,
    track_timecode=True,  # Enable timecode tracking
)
```

Note: Timecode accuracy depends on vMix configuration and video source.
For frame-accurate editing, ensure:
1. vMix is configured with correct frame rate
2. Video sources have embedded timecode (LTC/VITC)
3. Recording format preserves timecode metadata
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.vmix.client import VMixClient

logger = logging.getLogger(__name__)


# SMPTE Timecode constants
TIMECODE_PATTERN = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[:;](\d{2})$")
"""Pattern for SMPTE timecode: HH:MM:SS:FF or HH:MM:SS;FF (drop-frame)."""

DEFAULT_FRAME_RATE: float = 30.0
"""Default frame rate for timecode calculations (30 fps)."""


@dataclass
class SMPTETimecode:
    """SMPTE Timecode representation for frame-accurate synchronization.

    Attributes:
        hours: Hours component (0-23)
        minutes: Minutes component (0-59)
        seconds: Seconds component (0-59)
        frames: Frames component (0 to frame_rate-1)
        frame_rate: Video frame rate (default: 30.0)
        drop_frame: Whether using drop-frame timecode
    """

    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    frames: int = 0
    frame_rate: float = DEFAULT_FRAME_RATE
    drop_frame: bool = False

    def __str__(self) -> str:
        """Format as SMPTE string (HH:MM:SS:FF or HH:MM:SS;FF)."""
        separator = ";" if self.drop_frame else ":"
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{separator}{self.frames:02d}"

    def to_total_frames(self) -> int:
        """Convert to total frame count from midnight."""
        return (
            int(self.hours * 3600 * self.frame_rate)
            + int(self.minutes * 60 * self.frame_rate)
            + int(self.seconds * self.frame_rate)
            + self.frames
        )

    def to_seconds(self) -> float:
        """Convert to seconds (including fractional frame time)."""
        return (
            self.hours * 3600
            + self.minutes * 60
            + self.seconds
            + (self.frames / self.frame_rate)
        )

    @classmethod
    def from_string(
        cls,
        timecode_str: str,
        frame_rate: float = DEFAULT_FRAME_RATE,
    ) -> "SMPTETimecode | None":
        """Parse SMPTE timecode string.

        Args:
            timecode_str: String in format HH:MM:SS:FF or HH:MM:SS;FF
            frame_rate: Frame rate for validation

        Returns:
            SMPTETimecode instance or None if invalid
        """
        match = TIMECODE_PATTERN.match(timecode_str.strip())
        if not match:
            return None

        hours, minutes, seconds, frames = map(int, match.groups())
        drop_frame = ";" in timecode_str

        # Validate ranges
        if not (0 <= hours <= 23):
            return None
        if not (0 <= minutes <= 59):
            return None
        if not (0 <= seconds <= 59):
            return None
        if not (0 <= frames < int(frame_rate)):
            return None

        return cls(
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            frames=frames,
            frame_rate=frame_rate,
            drop_frame=drop_frame,
        )

    @classmethod
    def from_seconds(
        cls,
        total_seconds: float,
        frame_rate: float = DEFAULT_FRAME_RATE,
        drop_frame: bool = False,
    ) -> "SMPTETimecode":
        """Create from total seconds.

        Args:
            total_seconds: Time in seconds
            frame_rate: Frame rate
            drop_frame: Whether to use drop-frame format

        Returns:
            SMPTETimecode instance
        """
        total_frames = int(total_seconds * frame_rate)
        frames_per_second = int(frame_rate)
        frames_per_minute = frames_per_second * 60
        frames_per_hour = frames_per_minute * 60

        hours = total_frames // frames_per_hour
        total_frames %= frames_per_hour

        minutes = total_frames // frames_per_minute
        total_frames %= frames_per_minute

        seconds = total_frames // frames_per_second
        frames = total_frames % frames_per_second

        return cls(
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            frames=frames,
            frame_rate=frame_rate,
            drop_frame=drop_frame,
        )

    def __sub__(self, other: "SMPTETimecode") -> "SMPTETimecode":
        """Calculate duration between two timecodes."""
        diff_frames = self.to_total_frames() - other.to_total_frames()
        return SMPTETimecode.from_seconds(
            diff_frames / self.frame_rate,
            self.frame_rate,
            self.drop_frame,
        )


@dataclass
class HandRecordingResult:
    """Result of a hand recording session.

    Includes both wall-clock time and SMPTE timecode for frame-accurate editing.
    """

    table_id: str
    hand_number: int
    mark_in_time: datetime
    mark_out_time: datetime
    duration_seconds: int
    success: bool
    error_message: str | None = None

    # SMPTE Timecode fields (for frame-accurate editing)
    mark_in_timecode: SMPTETimecode | None = None
    mark_out_timecode: SMPTETimecode | None = None
    duration_timecode: SMPTETimecode | None = None

    @property
    def has_timecode(self) -> bool:
        """Check if timecode information is available."""
        return self.mark_in_timecode is not None and self.mark_out_timecode is not None

    def to_edl_entry(self, event_number: int = 1, reel_name: str = "001") -> str:
        """Generate EDL (Edit Decision List) entry for this recording.

        Args:
            event_number: EDL event number
            reel_name: Source reel name

        Returns:
            EDL entry string (CMX 3600 format)
        """
        if not self.has_timecode:
            return ""

        # CMX 3600 EDL format
        # EVENT REEL CHANNEL TRANS SOURCE_IN SOURCE_OUT RECORD_IN RECORD_OUT
        return (
            f"{event_number:03d}  {reel_name}  V     C        "
            f"{self.mark_in_timecode} {self.mark_out_timecode} "
            f"{self.mark_in_timecode} {self.mark_out_timecode}\n"
            f"* HAND: {self.table_id} #{self.hand_number}\n"
        )


class ReplayController:
    """Controls vMix Replay for hand-based recording.

    Manages mark-in/mark-out points and recording lifecycle
    for individual poker hands. Supports SMPTE timecode tracking
    for frame-accurate synchronization.

    Timecode Usage:
    ```python
    controller = ReplayController(client, frame_rate=30.0, track_timecode=True)
    await controller.start_hand_recording("table1", 42)
    # ... hand plays out ...
    result = await controller.end_hand_recording()
    print(f"In: {result.mark_in_timecode}, Out: {result.mark_out_timecode}")
    ```
    """

    def __init__(
        self,
        client: VMixClient,
        channel: str = "",
        on_recording_complete: Callable[[HandRecordingResult], None] | None = None,
        frame_rate: float = DEFAULT_FRAME_RATE,
        track_timecode: bool = False,
    ):
        """Initialize replay controller.

        Args:
            client: VMixClient instance
            channel: Replay channel to use (A, B, or empty for default)
            on_recording_complete: Optional callback when recording completes
            frame_rate: Video frame rate for timecode calculations (default: 30.0)
            track_timecode: Whether to track SMPTE timecodes (default: False)
        """
        self.client = client
        self.channel = channel
        self._on_recording_complete = on_recording_complete
        self.frame_rate = frame_rate
        self.track_timecode = track_timecode

        # Current recording state
        self._current_table_id: str | None = None
        self._current_hand_number: int | None = None
        self._mark_in_time: datetime | None = None
        self._mark_in_timecode: SMPTETimecode | None = None
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

    async def get_current_timecode(self) -> SMPTETimecode | None:
        """Get current SMPTE timecode from vMix.

        Returns:
            SMPTETimecode if available, None otherwise
        """
        try:
            state = await self.client.get_state()
            if state and hasattr(state, "timecode"):
                return SMPTETimecode.from_string(state.timecode, self.frame_rate)
        except Exception as e:
            logger.debug(f"Could not get timecode: {e}")
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

        # Capture timecode before mark-in (if enabled)
        if self.track_timecode:
            self._mark_in_timecode = await self.get_current_timecode()
            if self._mark_in_timecode:
                logger.debug(f"Mark-in timecode: {self._mark_in_timecode}")

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

            tc_info = f", TC: {self._mark_in_timecode}" if self._mark_in_timecode else ""
            logger.info(f"Mark-in set for hand {table_id} #{hand_number}{tc_info}")
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
        mark_in_timecode = self._mark_in_timecode

        logger.info(f"Ending hand recording: {table_id} #{hand_number}")

        # Capture mark-out timecode (if tracking enabled)
        mark_out_timecode: SMPTETimecode | None = None
        duration_timecode: SMPTETimecode | None = None
        if self.track_timecode:
            mark_out_timecode = await self.get_current_timecode()
            if mark_out_timecode:
                logger.debug(f"Mark-out timecode: {mark_out_timecode}")
            if mark_in_timecode and mark_out_timecode:
                duration_timecode = mark_out_timecode - mark_in_timecode
                logger.debug(f"Duration timecode: {duration_timecode}")

        # Mark out point
        success = await self.client.replay_mark_out(self.channel)
        mark_out_time = datetime.now()

        if success and mark_in_time:
            duration = int((mark_out_time - mark_in_time).total_seconds())

            result = HandRecordingResult(
                table_id=table_id or "unknown",
                hand_number=hand_number or 0,
                mark_in_time=mark_in_time,
                mark_out_time=mark_out_time,
                duration_seconds=duration,
                success=True,
                mark_in_timecode=mark_in_timecode,
                mark_out_timecode=mark_out_timecode,
                duration_timecode=duration_timecode,
            )

            tc_info = ""
            if mark_in_timecode and mark_out_timecode:
                tc_info = f", TC: {mark_in_timecode} -> {mark_out_timecode}"
            logger.info(
                f"Mark-out set for hand {table_id} #{hand_number}, "
                f"duration: {duration}s{tc_info}"
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
                table_id=table_id or "unknown",
                hand_number=hand_number or 0,
                mark_in_time=mark_in_time or mark_out_time,
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
        self._mark_in_timecode = None
        self._is_recording = False

    def get_current_duration(self) -> int | None:
        """Get duration of current recording in seconds.

        Returns:
            Duration in seconds, or None if not recording
        """
        if self._is_recording and self._mark_in_time:
            return int((datetime.now() - self._mark_in_time).total_seconds())
        return None
