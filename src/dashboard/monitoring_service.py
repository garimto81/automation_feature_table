"""Monitoring service for real-time data synchronization (PRD-0008 Phase 2).

Integrates with the main capture system to:
- Update table status in real-time
- Track hand grades as they're processed
- Sync recording session status
- Trigger alerts for failures and premium hands
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.monitoring_repository import MonitoringRepository
    from src.grading.grader import GradeResult
    from src.models.hand import FusedHandResult

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of monitoring alerts."""

    PRIMARY_DISCONNECTED = "primary_disconnected"
    SECONDARY_DISCONNECTED = "secondary_disconnected"
    PRIMARY_RECONNECTED = "primary_reconnected"
    SECONDARY_RECONNECTED = "secondary_reconnected"
    A_GRADE_HAND = "a_grade_hand"
    RECORDING_ERROR = "recording_error"
    SYSTEM_ERROR = "system_error"


@dataclass
class Alert:
    """Monitoring alert data."""

    alert_type: AlertType
    table_id: str | None
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: dict | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "type": self.alert_type.value,
            "table_id": self.table_id,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


# Type for alert callback
AlertCallback = Callable[[Alert], None]


class MonitoringService:
    """Service for real-time monitoring data synchronization.

    Usage:
        monitoring = MonitoringService(monitoring_repo)

        # In main system startup
        await monitoring.start()

        # When table status changes
        await monitoring.update_table_status(
            table_id="table_a",
            primary_connected=True,
            secondary_connected=True,
        )

        # When hand is processed
        await monitoring.on_hand_processed(fused_result, grade_result)

        # When recording starts/stops
        await monitoring.on_recording_started(table_id, session_id)
        await monitoring.on_recording_stopped(session_id, file_size_mb)
    """

    def __init__(
        self,
        monitoring_repo: "MonitoringRepository",
        on_alert: AlertCallback | None = None,
    ):
        self.repo = monitoring_repo
        self._on_alert = on_alert
        self._running = False

        # Track previous connection states for alert triggering
        self._prev_primary_states: dict[str, bool] = {}
        self._prev_secondary_states: dict[str, bool] = {}

        # Health check interval
        self._health_check_task: asyncio.Task | None = None
        self._health_check_interval = 30  # seconds

    async def start(self) -> None:
        """Start the monitoring service."""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Monitoring service started")

    async def stop(self) -> None:
        """Stop the monitoring service."""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Monitoring service stopped")

    # =========================================================================
    # Table Status Updates
    # =========================================================================

    async def update_table_status(
        self,
        table_id: str,
        primary_connected: bool | None = None,
        secondary_connected: bool | None = None,
        current_hand_id: int | None = None,
        current_hand_number: int | None = None,
        hand_start_time: datetime | None = None,
        fusion_result: str | None = None,
    ) -> None:
        """Update table status and trigger alerts if needed."""
        # Check for connection state changes and trigger alerts
        if primary_connected is not None:
            prev_state = self._prev_primary_states.get(table_id)
            if prev_state is not None and prev_state != primary_connected:
                if primary_connected:
                    self._trigger_alert(Alert(
                        alert_type=AlertType.PRIMARY_RECONNECTED,
                        table_id=table_id,
                        message=f"Primary (PokerGFX) reconnected for {table_id}",
                    ))
                else:
                    self._trigger_alert(Alert(
                        alert_type=AlertType.PRIMARY_DISCONNECTED,
                        table_id=table_id,
                        message=f"Primary (PokerGFX) disconnected for {table_id}",
                    ))
            self._prev_primary_states[table_id] = primary_connected

        if secondary_connected is not None:
            prev_state = self._prev_secondary_states.get(table_id)
            if prev_state is not None and prev_state != secondary_connected:
                if secondary_connected:
                    self._trigger_alert(Alert(
                        alert_type=AlertType.SECONDARY_RECONNECTED,
                        table_id=table_id,
                        message=f"Secondary (Gemini AI) reconnected for {table_id}",
                    ))
                else:
                    self._trigger_alert(Alert(
                        alert_type=AlertType.SECONDARY_DISCONNECTED,
                        table_id=table_id,
                        message=f"Secondary (Gemini AI) disconnected for {table_id}",
                    ))
            self._prev_secondary_states[table_id] = secondary_connected

        # Update database
        try:
            await self.repo.upsert_table_status(
                table_id=table_id,
                primary_connected=primary_connected,
                secondary_connected=secondary_connected,
                current_hand_id=current_hand_id,
                current_hand_number=current_hand_number,
                hand_start_time=hand_start_time,
                last_fusion_result=fusion_result,
            )
        except Exception as e:
            logger.error(f"Failed to update table status: {e}")

    async def clear_current_hand(self, table_id: str) -> None:
        """Clear current hand info when hand ends."""
        await self.update_table_status(
            table_id=table_id,
            current_hand_id=None,
            current_hand_number=None,
            hand_start_time=None,
        )

    # =========================================================================
    # Hand Processing Events
    # =========================================================================

    async def on_hand_started(
        self,
        table_id: str,
        hand_number: int,
        hand_id: int | None = None,
    ) -> None:
        """Called when a hand starts."""
        await self.update_table_status(
            table_id=table_id,
            current_hand_id=hand_id,
            current_hand_number=hand_number,
            hand_start_time=datetime.utcnow(),
        )

    async def on_hand_processed(
        self,
        result: "FusedHandResult",
        grade_result: "GradeResult",
        hand_id: int | None = None,
    ) -> None:
        """Called when a hand is processed and graded."""
        table_id = result.table_id

        # Determine fusion status
        fusion_status = "validated" if result.cross_validated else "review"
        if result.requires_review:
            fusion_status = "review"

        # Update table status
        await self.update_table_status(
            table_id=table_id,
            fusion_result=fusion_status,
        )

        # Trigger A-grade alert
        if grade_result.grade == "A":
            msg = f"A-Grade hand: {table_id} #{result.hand_number} - {result.rank_name}"
            self._trigger_alert(Alert(
                alert_type=AlertType.A_GRADE_HAND,
                table_id=table_id,
                message=msg,
                details={
                    "hand_number": result.hand_number,
                    "hand_rank": result.rank_name,
                    "hand_id": hand_id,
                    "is_premium": result.is_premium,
                    "cross_validated": result.cross_validated,
                },
            ))

        # Clear current hand (hand ended)
        await self.clear_current_hand(table_id)

        logger.debug(f"Hand processed: {table_id} #{result.hand_number} -> {grade_result.grade}")

    # =========================================================================
    # Recording Session Events
    # =========================================================================

    async def on_recording_started(
        self,
        table_id: str,
        session_id: str,
        vmix_input: int | None = None,
    ) -> None:
        """Called when a recording session starts."""
        try:
            await self.repo.create_recording_session(
                session_id=session_id,
                table_id=table_id,
                start_time=datetime.utcnow(),
                vmix_input=vmix_input,
            )
            logger.debug(f"Recording started: {session_id} for {table_id}")
        except Exception as e:
            logger.error(f"Failed to create recording session: {e}")

    async def on_recording_stopped(
        self,
        session_id: str,
        status: str = "completed",
        file_size_mb: float | None = None,
        file_path: str | None = None,
    ) -> None:
        """Called when a recording session stops."""
        try:
            await self.repo.update_recording_session(
                session_id=session_id,
                status=status,
                end_time=datetime.utcnow(),
                file_size_mb=file_size_mb,
                file_path=file_path,
            )
            logger.debug(f"Recording stopped: {session_id} ({status})")

            if status == "error":
                self._trigger_alert(Alert(
                    alert_type=AlertType.RECORDING_ERROR,
                    table_id=None,
                    message=f"Recording error for session {session_id}",
                    details={"session_id": session_id, "file_path": file_path},
                ))
        except Exception as e:
            logger.error(f"Failed to update recording session: {e}")

    # =========================================================================
    # System Health
    # =========================================================================

    async def log_service_health(
        self,
        service_name: str,
        status: str,
        latency_ms: int | None = None,
        message: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Log a health check for a service."""
        try:
            await self.repo.log_health(
                service_name=service_name,
                status=status,
                latency_ms=latency_ms,
                message=message,
                details=details,
            )

            if status == "error":
                self._trigger_alert(Alert(
                    alert_type=AlertType.SYSTEM_ERROR,
                    table_id=None,
                    message=f"Service error: {service_name} - {message}",
                    details={"service": service_name, "error": message},
                ))
        except Exception as e:
            logger.error(f"Failed to log service health: {e}")

    async def _health_check_loop(self) -> None:
        """Background loop for periodic health checks."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)

                if not self._running:
                    break

                # Log that monitoring service is alive
                await self.log_service_health(
                    service_name="MonitoringService",
                    status="connected",
                    message="Health check OK",
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    # =========================================================================
    # Alerts
    # =========================================================================

    def _trigger_alert(self, alert: Alert) -> None:
        """Trigger an alert."""
        logger.info(f"ALERT [{alert.alert_type.value}]: {alert.message}")

        if self._on_alert:
            try:
                self._on_alert(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

    def set_alert_callback(self, callback: AlertCallback | None) -> None:
        """Set or clear the alert callback."""
        self._on_alert = callback


class MonitoringIntegration:
    """Helper class to integrate MonitoringService with the main capture system.

    Usage in main.py:
        from src.dashboard.monitoring_service import MonitoringIntegration

        class PokerHandCaptureSystem:
            def __init__(self, settings):
                ...
                # Initialize monitoring integration
                self.monitoring = MonitoringIntegration(
                    db_manager=self.db_manager,
                    dashboard_websocket=self.dashboard,  # Optional
                )

            async def start(self):
                ...
                await self.monitoring.start()

            async def _handle_hand_start(self, table_id, hand_number):
                ...
                await self.monitoring.on_hand_started(table_id, hand_number)

            async def _process_fused_result(self, result):
                ...
                await self.monitoring.on_hand_processed(result, grade_result, hand_id)
    """

    def __init__(
        self,
        db_manager: "DatabaseManager",  # noqa: F821
        dashboard_websocket: "DashboardWebSocket | None" = None,  # noqa: F821
    ):
        from src.database.monitoring_repository import MonitoringRepository

        self.repo = MonitoringRepository(db_manager)
        self.service = MonitoringService(
            monitoring_repo=self.repo,
            on_alert=self._on_alert if dashboard_websocket else None,
        )
        self.dashboard = dashboard_websocket

    async def start(self) -> None:
        """Start monitoring integration."""
        await self.service.start()

    async def stop(self) -> None:
        """Stop monitoring integration."""
        await self.service.stop()

    def _on_alert(self, alert: Alert) -> None:
        """Handle alert by broadcasting to dashboard."""
        if self.dashboard:
            # Alerts will be included in next broadcast cycle
            # Could also implement immediate push here
            pass

    # Delegate methods to service
    async def on_hand_started(self, table_id: str, hand_number: int) -> None:
        await self.service.on_hand_started(table_id, hand_number)

    async def on_hand_processed(
        self,
        result: "FusedHandResult",
        grade_result: "GradeResult",
        hand_id: int | None = None,
    ) -> None:
        await self.service.on_hand_processed(result, grade_result, hand_id)

    async def update_primary_status(self, table_id: str, connected: bool) -> None:
        await self.service.update_table_status(table_id, primary_connected=connected)

    async def update_secondary_status(self, table_id: str, connected: bool) -> None:
        await self.service.update_table_status(table_id, secondary_connected=connected)

    async def on_recording_started(
        self, table_id: str, session_id: str, vmix_input: int | None = None
    ) -> None:
        await self.service.on_recording_started(table_id, session_id, vmix_input)

    async def on_recording_stopped(
        self,
        session_id: str,
        status: str = "completed",
        file_size_mb: float | None = None,
        file_path: str | None = None,
    ) -> None:
        await self.service.on_recording_stopped(session_id, status, file_size_mb, file_path)

    async def log_health(
        self,
        service_name: str,
        status: str,
        latency_ms: int | None = None,
        message: str | None = None,
    ) -> None:
        await self.service.log_service_health(service_name, status, latency_ms, message)
