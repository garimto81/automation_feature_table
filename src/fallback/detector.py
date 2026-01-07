"""Automation failure detection for fallback triggering."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import FallbackSettings

logger = logging.getLogger(__name__)


class FailureReason(Enum):
    """Reasons for automation failure."""

    PRIMARY_TIMEOUT = "primary_timeout"
    PRIMARY_DISCONNECTED = "primary_disconnected"
    SECONDARY_TIMEOUT = "secondary_timeout"
    SECONDARY_DISCONNECTED = "secondary_disconnected"
    SECONDARY_LOW_CONFIDENCE = "secondary_low_confidence"
    BOTH_FAILED = "both_failed"
    FUSION_MISMATCH = "fusion_mismatch"


@dataclass
class AutomationState:
    """Snapshot of current automation state."""

    primary_connected: bool = False
    secondary_connected: bool = False
    last_primary_event: datetime | None = None
    last_secondary_event: datetime | None = None
    primary_event_count: int = 0
    secondary_event_count: int = 0
    fusion_mismatch_count: int = 0
    last_mismatch_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for storage."""
        return {
            "primary_connected": self.primary_connected,
            "secondary_connected": self.secondary_connected,
            "last_primary_event": (
                self.last_primary_event.isoformat() if self.last_primary_event else None
            ),
            "last_secondary_event": (
                self.last_secondary_event.isoformat()
                if self.last_secondary_event
                else None
            ),
            "primary_event_count": self.primary_event_count,
            "secondary_event_count": self.secondary_event_count,
            "fusion_mismatch_count": self.fusion_mismatch_count,
        }


@dataclass
class FailureEvent:
    """Record of a failure event."""

    reason: FailureReason
    occurred_at: datetime
    state_snapshot: dict[str, object] = field(default_factory=dict)
    message: str | None = None


class FailureDetector:
    """Detects automation failures and triggers fallback mode.

    Monitors Primary (PokerGFX) and Secondary (Gemini) sources
    and triggers fallback when issues are detected.
    """

    def __init__(
        self,
        primary_timeout: int = 30,
        secondary_timeout: int = 60,
        mismatch_threshold: int = 3,
        on_fallback_triggered: Callable[[FailureReason, AutomationState], None] | None = None,
        on_fallback_reset: Callable[[], None] | None = None,
    ):
        """Initialize detector.

        Args:
            primary_timeout: Seconds without primary event before timeout
            secondary_timeout: Seconds without secondary event before timeout
            mismatch_threshold: Consecutive fusion mismatches before fallback
            on_fallback_triggered: Callback when fallback is triggered
            on_fallback_reset: Callback when fallback is reset
        """
        self.primary_timeout = primary_timeout
        self.secondary_timeout = secondary_timeout
        self.mismatch_threshold = mismatch_threshold
        self._on_fallback_triggered = on_fallback_triggered
        self._on_fallback_reset = on_fallback_reset

        self._state = AutomationState()
        self._fallback_active = False
        self._failure_history: list[FailureEvent] = []
        self._max_history = 100

    @classmethod
    def from_settings(
        cls,
        settings: "FallbackSettings",
        on_fallback_triggered: Callable[[FailureReason, AutomationState], None] | None = None,
        on_fallback_reset: Callable[[], None] | None = None,
    ) -> "FailureDetector":
        """Create detector from settings."""
        return cls(
            primary_timeout=settings.primary_timeout,
            secondary_timeout=settings.secondary_timeout,
            mismatch_threshold=settings.mismatch_threshold,
            on_fallback_triggered=on_fallback_triggered,
            on_fallback_reset=on_fallback_reset,
        )

    @property
    def is_fallback_active(self) -> bool:
        """Check if fallback mode is active."""
        return self._fallback_active

    @property
    def state(self) -> AutomationState:
        """Get current automation state."""
        return self._state

    def update_primary_status(
        self,
        connected: bool,
        event_received: bool = False,
    ) -> None:
        """Update primary source status.

        Args:
            connected: Whether primary is connected
            event_received: Whether an event was just received
        """
        was_connected = self._state.primary_connected
        self._state.primary_connected = connected

        if event_received:
            self._state.last_primary_event = datetime.now()
            self._state.primary_event_count += 1
            # Reset mismatch count on successful event
            self._state.fusion_mismatch_count = 0

        # Check for disconnect
        if was_connected and not connected:
            logger.warning("Primary source disconnected")
            self._check_for_failures()

        # Log reconnect
        if not was_connected and connected:
            logger.info("Primary source reconnected")

    def update_secondary_status(
        self,
        connected: bool,
        event_received: bool = False,
        confidence: float | None = None,
    ) -> None:
        """Update secondary source status.

        Args:
            connected: Whether secondary is connected
            event_received: Whether an event was just received
            confidence: Optional confidence score of the event
        """
        was_connected = self._state.secondary_connected
        self._state.secondary_connected = connected

        if event_received:
            self._state.last_secondary_event = datetime.now()
            self._state.secondary_event_count += 1

        # Check for low confidence
        if confidence is not None and confidence < 0.5:
            logger.warning(f"Secondary source low confidence: {confidence:.2f}")

        # Check for disconnect
        if was_connected and not connected:
            logger.warning("Secondary source disconnected")
            self._check_for_failures()

    def record_fusion_mismatch(self) -> None:
        """Record a fusion mismatch event."""
        self._state.fusion_mismatch_count += 1
        self._state.last_mismatch_at = datetime.now()

        logger.warning(
            f"Fusion mismatch recorded ({self._state.fusion_mismatch_count}/"
            f"{self.mismatch_threshold})"
        )

        if self._state.fusion_mismatch_count >= self.mismatch_threshold:
            self._trigger_fallback(FailureReason.FUSION_MISMATCH)

    def record_fusion_match(self) -> None:
        """Record a successful fusion match (resets mismatch count)."""
        if self._state.fusion_mismatch_count > 0:
            logger.debug("Fusion match - resetting mismatch count")
            self._state.fusion_mismatch_count = 0

    def check_timeouts(self) -> FailureReason | None:
        """Check for timeout conditions.

        Should be called periodically (e.g., every 5-10 seconds).

        Returns:
            FailureReason if timeout detected, None otherwise
        """
        now = datetime.now()

        # Check primary timeout
        if self._state.primary_connected and self._state.last_primary_event:
            elapsed = (now - self._state.last_primary_event).total_seconds()
            if elapsed > self.primary_timeout:
                logger.warning(f"Primary timeout: {elapsed:.1f}s since last event")
                return FailureReason.PRIMARY_TIMEOUT

        # Check secondary timeout (only if primary is also having issues)
        if not self._state.primary_connected:
            if self._state.secondary_connected and self._state.last_secondary_event:
                elapsed = (now - self._state.last_secondary_event).total_seconds()
                if elapsed > self.secondary_timeout:
                    logger.warning(
                        f"Secondary timeout: {elapsed:.1f}s since last event"
                    )
                    return FailureReason.SECONDARY_TIMEOUT

        return None

    def _check_for_failures(self) -> None:
        """Check current state for failure conditions."""
        # Both sources disconnected
        if not self._state.primary_connected and not self._state.secondary_connected:
            self._trigger_fallback(FailureReason.BOTH_FAILED)
            return

        # Primary disconnected, secondary can cover
        if not self._state.primary_connected and self._state.secondary_connected:
            # Allow secondary to cover for now, but log warning
            logger.warning("Primary disconnected, secondary covering")
            return

    def _trigger_fallback(self, reason: FailureReason) -> None:
        """Trigger fallback mode.

        Args:
            reason: Reason for triggering fallback
        """
        if self._fallback_active:
            logger.debug(f"Fallback already active, ignoring: {reason.value}")
            return

        self._fallback_active = True

        # Record failure event
        event = FailureEvent(
            reason=reason,
            occurred_at=datetime.now(),
            state_snapshot=self._state.to_dict(),
            message=f"Fallback triggered: {reason.value}",
        )
        self._add_to_history(event)

        logger.warning(f"FALLBACK TRIGGERED: {reason.value}")

        # Call callback
        if self._on_fallback_triggered:
            self._on_fallback_triggered(reason, self._state)

    def reset_fallback(self) -> None:
        """Reset fallback mode when automation recovers."""
        if not self._fallback_active:
            return

        self._fallback_active = False
        self._state.fusion_mismatch_count = 0

        logger.info("Fallback mode reset, automation resumed")

        if self._on_fallback_reset:
            self._on_fallback_reset()

    def _add_to_history(self, event: FailureEvent) -> None:
        """Add failure event to history."""
        self._failure_history.append(event)
        if len(self._failure_history) > self._max_history:
            self._failure_history = self._failure_history[-self._max_history:]

    def get_failure_history(self, limit: int = 20) -> list[FailureEvent]:
        """Get recent failure history."""
        return self._failure_history[-limit:]

    def get_stats(self) -> dict[str, object]:
        """Get detector statistics."""
        return {
            "fallback_active": self._fallback_active,
            "primary_connected": self._state.primary_connected,
            "secondary_connected": self._state.secondary_connected,
            "primary_events": self._state.primary_event_count,
            "secondary_events": self._state.secondary_event_count,
            "mismatch_count": self._state.fusion_mismatch_count,
            "failure_count": len(self._failure_history),
            "last_primary_event": (
                self._state.last_primary_event.isoformat()
                if self._state.last_primary_event
                else None
            ),
            "last_secondary_event": (
                self._state.last_secondary_event.isoformat()
                if self._state.last_secondary_event
                else None
            ),
        }
