"""Monitoring Service for real-time data synchronization (PRD-0008 Phase 2.2/2.3).

This service acts as the bridge between the main capture system and the dashboard,
synchronizing table status, hand grades, and recording sessions to the database.
Also provides alert system for connection failures and Grade A hand detection.

WebSocket Update Strategy:
-------------------------
The dashboard state is updated via `get_dashboard_state()` which should be called:

1. **Event-driven updates** (recommended for low-latency):
   - On hand completion (grade calculated)
   - On connection state change (primary/secondary)
   - On recording session start/stop
   - On Grade A hand detection (alert)

2. **Periodic polling** (fallback/backup):
   - Recommended interval: 5-10 seconds
   - Maximum interval: 30 seconds (beyond this, user experience degrades)

Example usage with WebSocket:
```python
# Event-driven (preferred)
async def on_hand_complete(result: FusedHandResult):
    await monitoring_service.update_fusion_result(table_id, result)
    state = await monitoring_service.get_dashboard_state()
    await websocket.broadcast(state)

# Periodic polling (backup)
async def periodic_sync():
    while True:
        state = await monitoring_service.get_dashboard_state()
        await websocket.broadcast(state)
        await asyncio.sleep(DASHBOARD_UPDATE_INTERVAL_SEC)
```

Constants:
- DASHBOARD_UPDATE_INTERVAL_SEC: Recommended polling interval (default: 5 seconds)
- DASHBOARD_MAX_STALENESS_SEC: Maximum acceptable staleness (default: 30 seconds)
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.dashboard.alerts import AlertManager

if TYPE_CHECKING:
    from src.database.connection import DatabaseManager
    from src.database.monitoring_repository import MonitoringRepository
    from src.grading.grader import GradeResult
    from src.models.hand import FusedHandResult
    from src.recording.session import RecordingSession

logger = logging.getLogger(__name__)

# WebSocket/Dashboard update configuration
DASHBOARD_UPDATE_INTERVAL_SEC: int = 5
"""Recommended polling interval for dashboard state updates (seconds).

Use event-driven updates when possible for lower latency.
This interval is for periodic backup polling.
"""

DASHBOARD_MAX_STALENESS_SEC: int = 30
"""Maximum acceptable staleness for dashboard data (seconds).

If the dashboard has not received an update within this time,
it should display a stale data warning to the user.
"""

HEALTH_CHECK_INTERVAL_SEC: int = 60
"""Interval for system health checks (seconds).

Health checks for PostgreSQL, PokerGFX, Gemini, vMix connections.
"""


class MonitoringService:
    """Service for synchronizing capture system state to monitoring database.

    Responsibilities:
    - Track table connection status (Primary/Secondary)
    - Update current hand information per table
    - Record hand grades for distribution statistics
    - Synchronize recording session states
    - Log system health status
    """

    def __init__(
        self,
        db_manager: "DatabaseManager",
        monitoring_repo: "MonitoringRepository | None" = None,
        alert_manager: AlertManager | None = None,
    ):
        self.db_manager = db_manager
        self._repo = monitoring_repo
        self._initialized = False

        # Alert manager for notifications (PRD-0008 Phase 2.3)
        self.alert_manager = alert_manager or AlertManager()

        # Cache for current state
        self._table_statuses: dict[str, dict[str, object]] = {}
        self._active_recordings: dict[str, str] = {}  # table_id -> session_id

    async def initialize(self) -> None:
        """Initialize the monitoring service."""
        if self._initialized:
            return

        # Lazy import to avoid circular dependency
        from src.database.monitoring_repository import MonitoringRepository

        if self._repo is None:
            self._repo = MonitoringRepository(self.db_manager)

        self._initialized = True
        logger.info("MonitoringService initialized")

    @property
    def repo(self) -> "MonitoringRepository":
        """Get the monitoring repository (must call initialize first)."""
        if self._repo is None:
            raise RuntimeError("MonitoringService not initialized. Call initialize() first.")
        return self._repo

    # =========================================================================
    # Table Status Updates
    # =========================================================================

    async def update_table_connection(
        self,
        table_id: str,
        primary_connected: bool | None = None,
        secondary_connected: bool | None = None,
    ) -> None:
        """Update table connection status.

        Args:
            table_id: Table identifier
            primary_connected: Primary (PokerGFX) connection status
            secondary_connected: Secondary (Gemini) connection status
        """
        if not self._initialized:
            return

        try:
            await self.repo.upsert_table_status(
                table_id=table_id,
                primary_connected=primary_connected,
                secondary_connected=secondary_connected,
            )

            # Check for connection state changes and generate alerts
            prev_state = self._table_statuses.get(table_id, {})

            if primary_connected is not None:
                prev_primary = prev_state.get("primary_connected")
                if prev_primary is True and primary_connected is False:
                    self.alert_manager.alert_connection_lost(table_id, "primary")
                elif prev_primary is False and primary_connected is True:
                    self.alert_manager.alert_connection_restored(table_id, "primary")

            if secondary_connected is not None:
                prev_secondary = prev_state.get("secondary_connected")
                if prev_secondary is True and secondary_connected is False:
                    self.alert_manager.alert_connection_lost(table_id, "secondary")
                elif prev_secondary is False and secondary_connected is True:
                    self.alert_manager.alert_connection_restored(table_id, "secondary")

            # Update cache
            if table_id not in self._table_statuses:
                self._table_statuses[table_id] = {}
            if primary_connected is not None:
                self._table_statuses[table_id]["primary_connected"] = primary_connected
            if secondary_connected is not None:
                self._table_statuses[table_id]["secondary_connected"] = secondary_connected

            logger.debug(f"Updated connection status for {table_id}")
        except Exception as e:
            logger.error(f"Failed to update table connection status: {e}")

    async def update_current_hand(
        self,
        table_id: str,
        hand_number: int,
        hand_start_time: datetime | None = None,
    ) -> None:
        """Update current hand information for a table.

        Args:
            table_id: Table identifier
            hand_number: Current hand number
            hand_start_time: When the hand started
        """
        if not self._initialized:
            return

        try:
            await self.repo.upsert_table_status(
                table_id=table_id,
                current_hand_number=hand_number,
                hand_start_time=hand_start_time or datetime.now(UTC),
            )
            logger.debug(f"Updated current hand for {table_id}: #{hand_number}")
        except Exception as e:
            logger.error(f"Failed to update current hand: {e}")

    async def update_fusion_result(
        self,
        table_id: str,
        result: "FusedHandResult",
    ) -> None:
        """Update table status with fusion result.

        Args:
            table_id: Table identifier
            result: Fused hand result
        """
        if not self._initialized:
            return

        try:
            # Determine fusion result type
            from src.models.hand import SourceType

            if result.cross_validated:
                fusion_result = "validated"
            elif result.requires_review:
                fusion_result = "review"
            elif result.source == SourceType.SECONDARY:
                fusion_result = "fallback"
            else:
                fusion_result = "primary_only"

            await self.repo.upsert_table_status(
                table_id=table_id,
                last_fusion_result=fusion_result,
            )
            logger.debug(f"Updated fusion result for {table_id}: {fusion_result}")
        except Exception as e:
            logger.error(f"Failed to update fusion result: {e}")

    # =========================================================================
    # Hand Grade Updates
    # =========================================================================

    async def record_hand_grade(
        self,
        hand_id: int,
        grade_result: "GradeResult",
        table_id: str | None = None,
        hand_number: int | None = None,
    ) -> None:
        """Record hand grade for statistics and generate alerts.

        Note: Grade is already saved via HandRepository.save_hand().
        This method is for explicit grade updates or recalculations.

        Args:
            hand_id: Database hand ID
            grade_result: Grade result from HandGrader
            table_id: Optional table identifier for alert
            hand_number: Optional hand number for alert
        """
        if not self._initialized:
            return

        # Generate alert for Grade A hands
        if grade_result.grade == "A" and table_id and hand_number:
            conditions_met = []
            if grade_result.has_premium_hand:
                conditions_met.append("premium_hand")
            if grade_result.has_long_playtime:
                conditions_met.append("long_playtime")
            if grade_result.has_premium_board_combo:
                conditions_met.append("board_combo")

            self.alert_manager.alert_grade_a_hand(
                table_id=table_id,
                hand_number=hand_number,
                hand_rank="Premium Hand",  # GradeResult doesn't store rank name
                conditions_met=conditions_met,
            )

        # The grade is saved via the existing HandRepository flow
        # This method can be used for explicit updates if needed
        logger.debug(f"Hand {hand_id} graded: {grade_result.grade}")

    # =========================================================================
    # Recording Session Updates
    # =========================================================================

    async def start_recording_session(
        self,
        table_id: str,
        hand_number: int,
        session_id: str | None = None,
    ) -> str | None:
        """Start a new recording session.

        Args:
            table_id: Table identifier
            hand_number: Current hand number
            session_id: Optional custom session ID

        Returns:
            Session ID if created successfully, None otherwise
        """
        if not self._initialized:
            return None

        try:
            # Generate session ID if not provided
            if session_id is None:
                session_id = f"{table_id}_{hand_number}_{datetime.now(UTC).strftime('%H%M%S')}"

            session = await self.repo.create_recording_session(
                session_id=session_id,
                table_id=table_id,
                start_time=datetime.now(UTC),
            )

            if session:
                self._active_recordings[table_id] = session_id
                logger.info(f"Started recording session: {session_id}")
                return session_id
        except Exception as e:
            logger.error(f"Failed to start recording session: {e}")

        return None

    async def stop_recording_session(
        self,
        table_id: str,
        file_path: str | None = None,
        file_size_mb: float | None = None,
    ) -> None:
        """Stop a recording session.

        Args:
            table_id: Table identifier
            file_path: Path to recorded file
            file_size_mb: File size in MB
        """
        if not self._initialized:
            return

        session_id = self._active_recordings.pop(table_id, None)
        if not session_id:
            logger.debug(f"No active recording session for {table_id}")
            return

        try:
            await self.repo.update_recording_session(
                session_id=session_id,
                status="completed",
                end_time=datetime.now(UTC),
                file_path=file_path,
                file_size_mb=file_size_mb,
            )
            logger.info(f"Stopped recording session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to stop recording session: {e}")

    async def update_recording_file_info(
        self,
        session: "RecordingSession",
    ) -> None:
        """Update recording session with file information.

        Args:
            session: Recording session with file info
        """
        if not self._initialized:
            return

        session_id = self._active_recordings.get(session.table_id)
        if not session_id:
            return

        try:
            file_size_mb = (
                session.file_size_bytes / (1024 * 1024)
                if session.file_size_bytes
                else None
            )
            await self.repo.update_recording_session(
                session_id=session_id,
                file_path=session.file_path,
                file_size_mb=file_size_mb,
            )
        except Exception as e:
            logger.error(f"Failed to update recording file info: {e}")

    # =========================================================================
    # System Health Updates
    # =========================================================================

    async def log_health(
        self,
        service_name: str,
        status: str,
        latency_ms: int | None = None,
        message: str | None = None,
    ) -> None:
        """Log system health status.

        Args:
            service_name: Name of the service (PostgreSQL, PokerGFX, Gemini, vMix)
            status: Status string (connected, disconnected, error)
            latency_ms: Response latency in milliseconds
            message: Additional status message
        """
        if not self._initialized:
            return

        try:
            await self.repo.log_health(
                service_name=service_name,
                status=status,
                latency_ms=latency_ms,
                message=message,
            )
            logger.debug(f"Logged health for {service_name}: {status}")
        except Exception as e:
            logger.error(f"Failed to log health status: {e}")

    async def check_and_log_vmix_health(
        self,
        vmix_client: object,
    ) -> None:
        """Check and log vMix connection health.

        Args:
            vmix_client: VMixClient instance
        """
        if not self._initialized:
            return

        try:
            from src.vmix.client import VMixClient
            if isinstance(vmix_client, VMixClient):
                start = datetime.now(UTC)
                connected = await vmix_client.ping()
                latency = int((datetime.now(UTC) - start).total_seconds() * 1000)

                await self.log_health(
                    service_name="vMix",
                    status="connected" if connected else "disconnected",
                    latency_ms=latency if connected else None,
                    message="Recording" if connected else None,
                )
        except Exception as e:
            await self.log_health(
                service_name="vMix",
                status="error",
                message=str(e),
            )

    # =========================================================================
    # Batch Updates
    # =========================================================================

    async def sync_all_table_statuses(
        self,
        table_ids: list[str],
        primary_connected: bool,
        secondary_connected: bool,
    ) -> None:
        """Sync connection status for all tables.

        Args:
            table_ids: List of table identifiers
            primary_connected: Primary connection status
            secondary_connected: Secondary connection status
        """
        for table_id in table_ids:
            await self.update_table_connection(
                table_id=table_id,
                primary_connected=primary_connected,
                secondary_connected=secondary_connected,
            )

    async def get_dashboard_state(self) -> dict[str, object]:
        """Get current dashboard state for WebSocket broadcasting.

        Returns:
            Dictionary with table_statuses, grade_distribution, etc.
        """
        if not self._initialized:
            return {}

        try:
            table_statuses = await self.repo.get_all_table_statuses()
            grade_dist = await self.repo.get_grade_distribution()
            active_recordings = await self.repo.get_active_recording_sessions()
            health_logs = await self.repo.get_all_latest_health()
            today_stats = await self.repo.get_today_stats()

            return {
                "table_statuses": [
                    {
                        "table_id": s.table_id,
                        "primary_connected": s.primary_connected,
                        "secondary_connected": s.secondary_connected,
                        "current_hand_number": s.current_hand_number,
                        "hand_start_time": (
                            s.hand_start_time.isoformat() if s.hand_start_time else None
                        ),
                        "last_fusion_result": s.last_fusion_result,
                    }
                    for s in table_statuses
                ],
                "grade_distribution": grade_dist,
                "recording_sessions": [
                    {
                        "session_id": r.session_id,
                        "table_id": r.table_id,
                        "status": r.status,
                        "start_time": r.start_time.isoformat() if r.start_time else None,
                        "file_size_mb": r.file_size_mb,
                    }
                    for r in active_recordings
                ],
                "system_health": {
                    log.service_name: {
                        "status": log.status,
                        "latency_ms": log.latency_ms,
                        "message": log.message,
                        "last_check": log.created_at.isoformat(),
                    }
                    for log in health_logs.values()
                },
                "today_stats": today_stats,
                "last_updated": datetime.now(UTC).isoformat(),
                # Alert information (PRD-0008 Phase 2.3)
                "alerts": {
                    "active": [a.to_dict() for a in self.alert_manager.get_active_alerts()],
                    "counts": self.alert_manager.get_alert_counts(),
                },
            }
        except Exception as e:
            logger.error(f"Failed to get dashboard state: {e}")
            return {}
