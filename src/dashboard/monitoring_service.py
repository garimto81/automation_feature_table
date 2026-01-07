"""Monitoring Service for real-time data synchronization (PRD-0008 Phase 2.2).

This service acts as the bridge between the main capture system and the dashboard,
synchronizing table status, hand grades, and recording sessions to the database.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.connection import DatabaseManager
    from src.database.monitoring_repository import MonitoringRepository
    from src.grading.grader import GradeResult
    from src.models.hand import FusedHandResult
    from src.recording.session import RecordingSession

logger = logging.getLogger(__name__)


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
    ):
        self.db_manager = db_manager
        self._repo = monitoring_repo
        self._initialized = False

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
    ) -> None:
        """Record hand grade for statistics.

        Note: Grade is already saved via HandRepository.save_hand().
        This method is for explicit grade updates or recalculations.
        """
        if not self._initialized:
            return

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
            await self.repo.update_recording_session(
                session_id=session_id,
                file_path=session.file_path,
                file_size_mb=session.file_size_mb,
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
            health_logs = await self.repo.get_latest_health_logs()
            today_stats = await self.repo.get_today_stats()

            return {
                "table_statuses": [
                    {
                        "table_id": s.table_id,
                        "primary_connected": s.primary_connected,
                        "secondary_connected": s.secondary_connected,
                        "current_hand_number": s.current_hand_number,
                        "hand_start_time": s.hand_start_time.isoformat() if s.hand_start_time else None,
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
            }
        except Exception as e:
            logger.error(f"Failed to get dashboard state: {e}")
            return {}
