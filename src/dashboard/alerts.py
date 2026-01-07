"""Alert system for monitoring dashboard (PRD-0008 Phase 2.3).

Provides real-time alerts for:
- Connection failures (Primary/Secondary disconnection)
- Grade A hand detection
- System health issues
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of alerts."""

    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    GRADE_A_HAND = "grade_a_hand"
    SYSTEM_ERROR = "system_error"
    HEALTH_WARNING = "health_warning"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Represents a single alert."""

    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    table_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    id: str = ""

    def __post_init__(self) -> None:
        """Generate alert ID if not provided."""
        if not self.id:
            ts = self.timestamp.strftime("%Y%m%d%H%M%S%f")
            unique = uuid.uuid4().hex[:8]
            self.id = f"{self.alert_type.value}_{ts}_{unique}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "table_id": self.table_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "acknowledged": self.acknowledged,
        }


# Type alias for alert handlers
AlertHandler = (
    Callable[[Alert], None] | Callable[[Alert], Awaitable[None]]
)


class AlertManager:
    """Manages alerts and notifications.

    Responsibilities:
    - Create and store alerts
    - Notify registered handlers (WebSocket broadcast, etc.)
    - Track alert history
    - Handle alert acknowledgment
    """

    def __init__(
        self,
        max_history: int = 100,
        on_alert: AlertHandler | None = None,
    ):
        self._alerts: list[Alert] = []
        self._max_history = max_history
        self._on_alert = on_alert

        # Track connection states to avoid duplicate alerts
        self._connection_states: dict[str, dict[str, bool]] = {}

    def _add_alert(self, alert: Alert) -> None:
        """Add alert to history and notify handlers."""
        self._alerts.append(alert)

        # Trim history if needed
        if len(self._alerts) > self._max_history:
            self._alerts = self._alerts[-self._max_history :]

        logger.info(
            f"Alert [{alert.severity.value.upper()}] {alert.title}: {alert.message}"
        )

        # Notify handler (sync only for now, async handled by caller)
        if self._on_alert and not hasattr(self._on_alert, "__await__"):
            try:
                self._on_alert(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

    def alert_connection_lost(
        self,
        table_id: str,
        source: str,  # "primary" or "secondary"
    ) -> Alert:
        """Create alert for connection loss.

        Args:
            table_id: Table identifier
            source: Connection source ("primary" or "secondary")

        Returns:
            Created Alert object
        """
        # Check if already in disconnected state
        table_state = self._connection_states.setdefault(table_id, {})
        if not table_state.get(f"{source}_connected", True):
            # Already disconnected, don't create duplicate alert
            return Alert(
                alert_type=AlertType.CONNECTION_LOST,
                severity=AlertSeverity.WARNING,
                title=f"{source.title()} Disconnected (duplicate)",
                message=f"Already tracking disconnection for {table_id}",
                table_id=table_id,
            )

        # Update state
        table_state[f"{source}_connected"] = False

        source_name = "PokerGFX RFID" if source == "primary" else "Gemini AI Video"
        alert = Alert(
            alert_type=AlertType.CONNECTION_LOST,
            severity=AlertSeverity.ERROR,
            title=f"{source_name} Disconnected",
            message=f"Table {table_id}: {source_name} connection lost. Fallback mode may activate.",
            table_id=table_id,
            metadata={"source": source},
        )

        self._add_alert(alert)
        return alert

    def alert_connection_restored(
        self,
        table_id: str,
        source: str,
    ) -> Alert:
        """Create alert for connection restoration.

        Args:
            table_id: Table identifier
            source: Connection source ("primary" or "secondary")

        Returns:
            Created Alert object
        """
        # Update state
        table_state = self._connection_states.setdefault(table_id, {})
        was_disconnected = not table_state.get(f"{source}_connected", True)
        table_state[f"{source}_connected"] = True

        if not was_disconnected:
            # Wasn't disconnected, don't create alert
            return Alert(
                alert_type=AlertType.CONNECTION_RESTORED,
                severity=AlertSeverity.INFO,
                title=f"{source.title()} Connected (no prior disconnection)",
                message=f"Connection was already active for {table_id}",
                table_id=table_id,
            )

        source_name = "PokerGFX RFID" if source == "primary" else "Gemini AI Video"
        alert = Alert(
            alert_type=AlertType.CONNECTION_RESTORED,
            severity=AlertSeverity.INFO,
            title=f"{source_name} Restored",
            message=f"Table {table_id}: {source_name} connection restored.",
            table_id=table_id,
            metadata={"source": source},
        )

        self._add_alert(alert)
        return alert

    def alert_grade_a_hand(
        self,
        table_id: str,
        hand_number: int,
        hand_rank: str,
        conditions_met: list[str],
    ) -> Alert:
        """Create alert for Grade A hand detection.

        Args:
            table_id: Table identifier
            hand_number: Hand number
            hand_rank: Hand ranking (e.g., "Full House")
            conditions_met: List of conditions met for Grade A

        Returns:
            Created Alert object
        """
        alert = Alert(
            alert_type=AlertType.GRADE_A_HAND,
            severity=AlertSeverity.INFO,
            title="Grade A Hand Detected",
            message=(
                f"Table {table_id} Hand #{hand_number}: {hand_rank} - "
                f"Broadcast-ready content!"
            ),
            table_id=table_id,
            metadata={
                "hand_number": hand_number,
                "hand_rank": hand_rank,
                "conditions_met": conditions_met,
            },
        )

        self._add_alert(alert)
        return alert

    def alert_system_error(
        self,
        service_name: str,
        error_message: str,
        table_id: str | None = None,
    ) -> Alert:
        """Create alert for system error.

        Args:
            service_name: Name of the service with error
            error_message: Error description
            table_id: Optional table identifier

        Returns:
            Created Alert object
        """
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.ERROR,
            title=f"{service_name} Error",
            message=error_message,
            table_id=table_id,
            metadata={"service": service_name},
        )

        self._add_alert(alert)
        return alert

    def alert_health_warning(
        self,
        service_name: str,
        warning_message: str,
        latency_ms: int | None = None,
    ) -> Alert:
        """Create alert for health warning.

        Args:
            service_name: Name of the service
            warning_message: Warning description
            latency_ms: Optional latency value

        Returns:
            Created Alert object
        """
        metadata: dict[str, Any] = {"service": service_name}
        if latency_ms is not None:
            metadata["latency_ms"] = latency_ms

        alert = Alert(
            alert_type=AlertType.HEALTH_WARNING,
            severity=AlertSeverity.WARNING,
            title=f"{service_name} Health Warning",
            message=warning_message,
            metadata=metadata,
        )

        self._add_alert(alert)
        return alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: Alert identifier

        Returns:
            True if alert was found and acknowledged
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                logger.info(f"Alert acknowledged: {alert_id}")
                return True
        return False

    def get_alerts(
        self,
        unacknowledged_only: bool = False,
        severity: AlertSeverity | None = None,
        alert_type: AlertType | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        """Get alerts with optional filtering.

        Args:
            unacknowledged_only: Only return unacknowledged alerts
            severity: Filter by severity level
            alert_type: Filter by alert type
            limit: Maximum number of alerts to return

        Returns:
            List of alerts matching filters
        """
        alerts = self._alerts.copy()
        alerts.reverse()  # Most recent first

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        return alerts[:limit]

    def get_active_alerts(self) -> list[Alert]:
        """Get active (unacknowledged) alerts.

        Returns:
            List of unacknowledged alerts
        """
        return self.get_alerts(unacknowledged_only=True)

    def get_alert_counts(self) -> dict[str, int]:
        """Get alert counts by type.

        Returns:
            Dictionary with alert type counts
        """
        counts: dict[str, int] = {
            "total": len(self._alerts),
            "unacknowledged": len([a for a in self._alerts if not a.acknowledged]),
        }

        for alert_type in AlertType:
            counts[alert_type.value] = len(
                [a for a in self._alerts if a.alert_type == alert_type]
            )

        return counts

    def clear_acknowledged(self) -> int:
        """Clear all acknowledged alerts.

        Returns:
            Number of alerts cleared
        """
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if not a.acknowledged]
        cleared = before - len(self._alerts)
        logger.info(f"Cleared {cleared} acknowledged alerts")
        return cleared
