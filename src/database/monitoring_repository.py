"""Repository for monitoring dashboard data (PRD-0008)."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from src.database.models import (
    Grade,
    Hand,
    RecordingSession,
    SystemHealthLog,
    TableStatus,
)

if TYPE_CHECKING:
    from src.database.connection import DatabaseManager

logger = logging.getLogger(__name__)


class MonitoringRepository:
    """Repository for monitoring dashboard operations (PRD-0008)."""

    def __init__(self, db_manager: "DatabaseManager"):
        self.db_manager = db_manager

    # =========================================================================
    # Table Status
    # =========================================================================

    async def upsert_table_status(
        self,
        table_id: str,
        primary_connected: bool | None = None,
        secondary_connected: bool | None = None,
        current_hand_id: int | None = None,
        current_hand_number: int | None = None,
        hand_start_time: datetime | None = None,
        last_fusion_result: str | None = None,
    ) -> TableStatus:
        """Create or update table status."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(TableStatus).where(TableStatus.table_id == table_id)
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = TableStatus(table_id=table_id)
                session.add(status)

            if primary_connected is not None:
                status.primary_connected = primary_connected
            if secondary_connected is not None:
                status.secondary_connected = secondary_connected
            if current_hand_id is not None:
                status.current_hand_id = current_hand_id
            if current_hand_number is not None:
                status.current_hand_number = current_hand_number
            if hand_start_time is not None:
                status.hand_start_time = hand_start_time
            if last_fusion_result is not None:
                status.last_fusion_result = last_fusion_result

            status.updated_at = datetime.utcnow()
            await session.flush()

            logger.debug(f"Updated table status for {table_id}")
            return status

    async def get_all_table_statuses(self) -> list[TableStatus]:
        """Get all table statuses."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(TableStatus).order_by(TableStatus.table_id)
            )
            return list(result.scalars().all())

    async def get_table_status(self, table_id: str) -> TableStatus | None:
        """Get status for a specific table."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(TableStatus).where(TableStatus.table_id == table_id)
            )
            return result.scalar_one_or_none()

    # =========================================================================
    # System Health
    # =========================================================================

    async def log_health(
        self,
        service_name: str,
        status: str,
        latency_ms: int | None = None,
        message: str | None = None,
        details: dict | None = None,
    ) -> SystemHealthLog:
        """Log a system health check."""
        async with self.db_manager.session() as session:
            log = SystemHealthLog(
                service_name=service_name,
                status=status,
                latency_ms=latency_ms,
                message=message,
                details=details,
            )
            session.add(log)
            await session.flush()

            logger.debug(f"Logged health for {service_name}: {status}")
            return log

    async def get_latest_health(self, service_name: str) -> SystemHealthLog | None:
        """Get the latest health log for a service."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(SystemHealthLog)
                .where(SystemHealthLog.service_name == service_name)
                .order_by(SystemHealthLog.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_all_latest_health(self) -> dict[str, SystemHealthLog]:
        """Get the latest health status for all services."""
        async with self.db_manager.session() as session:
            # Subquery to get max timestamp per service
            subq = (
                select(
                    SystemHealthLog.service_name,
                    func.max(SystemHealthLog.created_at).label("max_created_at"),
                )
                .group_by(SystemHealthLog.service_name)
                .subquery()
            )

            result = await session.execute(
                select(SystemHealthLog).join(
                    subq,
                    (SystemHealthLog.service_name == subq.c.service_name)
                    & (SystemHealthLog.created_at == subq.c.max_created_at),
                )
            )

            return {log.service_name: log for log in result.scalars().all()}

    async def get_health_history(
        self,
        service_name: str,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[SystemHealthLog]:
        """Get health log history for a service."""
        async with self.db_manager.session() as session:
            query = select(SystemHealthLog).where(
                SystemHealthLog.service_name == service_name
            )
            if since:
                query = query.where(SystemHealthLog.created_at >= since)
            query = query.order_by(SystemHealthLog.created_at.desc()).limit(limit)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def cleanup_old_health_logs(self, before: datetime) -> int:
        """Delete health logs older than the specified time."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                delete(SystemHealthLog).where(SystemHealthLog.created_at < before)
            )
            deleted = result.rowcount
            logger.info(f"Deleted {deleted} old health logs")
            return deleted

    # =========================================================================
    # Recording Sessions
    # =========================================================================

    async def create_recording_session(
        self,
        session_id: str,
        table_id: str,
        start_time: datetime,
        vmix_input: int | None = None,
    ) -> RecordingSession:
        """Create a new recording session."""
        async with self.db_manager.session() as session:
            rec_session = RecordingSession(
                session_id=session_id,
                table_id=table_id,
                start_time=start_time,
                status="recording",
                vmix_input=vmix_input,
            )
            session.add(rec_session)
            await session.flush()

            logger.info(f"Created recording session {session_id} for {table_id}")
            return rec_session

    async def update_recording_session(
        self,
        session_id: str,
        status: str | None = None,
        end_time: datetime | None = None,
        file_size_mb: float | None = None,
        file_path: str | None = None,
    ) -> RecordingSession | None:
        """Update a recording session."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(RecordingSession).where(RecordingSession.session_id == session_id)
            )
            rec_session = result.scalar_one_or_none()

            if rec_session is None:
                logger.warning(f"Recording session {session_id} not found")
                return None

            if status is not None:
                rec_session.status = status
            if end_time is not None:
                rec_session.end_time = end_time
            if file_size_mb is not None:
                rec_session.file_size_mb = file_size_mb
            if file_path is not None:
                rec_session.file_path = file_path

            rec_session.updated_at = datetime.utcnow()
            await session.flush()

            logger.debug(f"Updated recording session {session_id}")
            return rec_session

    async def get_active_recording_sessions(self) -> list[RecordingSession]:
        """Get all active (recording) sessions."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(RecordingSession)
                .where(RecordingSession.status == "recording")
                .order_by(RecordingSession.start_time.desc())
            )
            return list(result.scalars().all())

    async def get_recording_sessions_by_table(
        self, table_id: str, limit: int = 20
    ) -> list[RecordingSession]:
        """Get recording sessions for a table."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(RecordingSession)
                .where(RecordingSession.table_id == table_id)
                .order_by(RecordingSession.start_time.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_today_completed_sessions(self) -> list[RecordingSession]:
        """Get today's completed recording sessions."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(RecordingSession)
                .where(
                    RecordingSession.status == "completed",
                    RecordingSession.end_time >= today_start,
                )
                .order_by(RecordingSession.end_time.desc())
            )
            return list(result.scalars().all())

    # =========================================================================
    # Dashboard Aggregations
    # =========================================================================

    async def get_grade_distribution(
        self, since: datetime | None = None
    ) -> dict[str, int]:
        """Get hand grade distribution (A/B/C counts)."""
        async with self.db_manager.session() as session:
            query = select(Grade.grade, func.count(Grade.id)).group_by(Grade.grade)

            if since:
                query = query.join(Hand).where(Hand.started_at >= since)

            result = await session.execute(query)
            return {row[0]: row[1] for row in result.all()}

    async def get_recent_premium_hands(self, limit: int = 10) -> list[Hand]:
        """Get recent A-grade hands."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(Hand)
                .join(Grade)
                .where(Grade.grade == "A")
                .order_by(Hand.started_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_broadcast_eligible_count(
        self, since: datetime | None = None
    ) -> int:
        """Get count of broadcast-eligible hands (A+B grades)."""
        async with self.db_manager.session() as session:
            query = select(func.count(Grade.id)).where(
                Grade.broadcast_eligible == True  # noqa: E712
            )

            if since:
                query = query.join(Hand).where(Hand.started_at >= since)

            result = await session.execute(query)
            return result.scalar() or 0

    async def get_today_stats(self) -> dict:
        """Get aggregated stats for today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        grade_dist = await self.get_grade_distribution(since=today_start)
        broadcast_count = await self.get_broadcast_eligible_count(since=today_start)
        completed_sessions = await self.get_today_completed_sessions()

        total_hands = sum(grade_dist.values())
        total_size_gb = sum(s.file_size_mb or 0 for s in completed_sessions) / 1024

        return {
            "total_hands": total_hands,
            "grade_distribution": grade_dist,
            "broadcast_eligible": broadcast_count,
            "broadcast_ratio": (
                round(broadcast_count / total_hands * 100, 1) if total_hands > 0 else 0
            ),
            "completed_sessions": len(completed_sessions),
            "total_storage_gb": round(total_size_gb, 2),
        }
