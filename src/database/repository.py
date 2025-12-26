"""Repository for database CRUD operations."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from src.database.models import Grade, Hand, ManualMark, Recording

if TYPE_CHECKING:
    from src.database.connection import DatabaseManager
    from src.grading.grader import GradeResult
    from src.models.hand import FusedHandResult

logger = logging.getLogger(__name__)


class HandRepository:
    """Repository for hand-related database operations."""

    def __init__(self, db_manager: "DatabaseManager"):
        self.db_manager = db_manager

    async def save_hand(
        self,
        result: "FusedHandResult",
        grade_result: Optional["GradeResult"] = None,
    ) -> Hand:
        """Save a fused hand result to the database."""
        async with self.db_manager.session() as session:
            # Create hand record
            hand = Hand(
                table_id=result.table_id,
                hand_number=result.hand_number,
                started_at=result.timestamp,
                ended_at=datetime.utcnow(),
                community_cards=[str(c) for c in result.community_cards] if result.community_cards else None,
                players_data=result.players_data if hasattr(result, "players_data") else None,
                hand_rank=result.rank_name,
                rank_value=result.rank_value,
                is_premium=result.is_premium,
                source=result.source.value,
                primary_confidence=result.confidence if result.source.value == "primary" else None,
                secondary_confidence=result.confidence if result.source.value == "secondary" else None,
                cross_validated=result.cross_validated,
                requires_review=result.requires_review,
            )

            session.add(hand)
            await session.flush()

            # Add grade if provided
            if grade_result:
                grade = Grade(
                    hand_id=hand.id,
                    grade=grade_result.grade,
                    has_premium_hand=grade_result.has_premium_hand,
                    has_long_playtime=grade_result.has_long_playtime,
                    has_premium_board_combo=grade_result.has_premium_board_combo,
                    conditions_met=grade_result.conditions_met,
                    broadcast_eligible=grade_result.broadcast_eligible,
                    suggested_edit_start_offset=grade_result.suggested_edit_offset,
                    edit_start_confidence=grade_result.edit_confidence,
                    graded_by="auto",
                )
                session.add(grade)

            logger.info(f"Saved hand {result.table_id} #{result.hand_number} to database")
            return hand

    async def save_recording(
        self,
        hand_id: int,
        file_path: str,
        file_name: str,
        recording_started_at: datetime,
        recording_ended_at: datetime | None = None,
        duration_seconds: int | None = None,
        vmix_input_number: int | None = None,
        status: str = "completed",
    ) -> Recording:
        """Save a recording record linked to a hand."""
        async with self.db_manager.session() as session:
            recording = Recording(
                hand_id=hand_id,
                file_path=file_path,
                file_name=file_name,
                recording_started_at=recording_started_at,
                recording_ended_at=recording_ended_at,
                duration_seconds=duration_seconds,
                vmix_input_number=vmix_input_number,
                status=status,
            )
            session.add(recording)
            await session.flush()

            logger.info(f"Saved recording {file_name} for hand_id={hand_id}")
            return recording

    async def save_manual_mark(
        self,
        table_id: str,
        mark_type: str,
        marked_at: datetime,
        hand_id: int | None = None,
        fallback_reason: str | None = None,
        automation_state: dict | None = None,
        marked_by: str | None = None,
    ) -> ManualMark:
        """Save a manual mark record."""
        async with self.db_manager.session() as session:
            mark = ManualMark(
                table_id=table_id,
                mark_type=mark_type,
                marked_at=marked_at,
                hand_id=hand_id,
                fallback_reason=fallback_reason,
                automation_state=automation_state,
                marked_by=marked_by,
            )
            session.add(mark)
            await session.flush()

            logger.info(f"Saved manual mark {mark_type} for {table_id}")
            return mark

    async def get_hand_by_id(self, hand_id: int) -> Hand | None:
        """Get a hand by ID."""
        async with self.db_manager.session() as session:
            result = await session.execute(select(Hand).where(Hand.id == hand_id))
            return result.scalar_one_or_none()

    async def get_hands_by_table(
        self,
        table_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Hand]:
        """Get hands for a specific table."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(Hand)
                .where(Hand.table_id == table_id)
                .order_by(Hand.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_broadcast_eligible_hands(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Hand]:
        """Get hands that are eligible for broadcast (grade A or B)."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(Hand)
                .join(Grade)
                .where(Grade.broadcast_eligible == True)  # noqa: E712
                .order_by(Hand.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get_hands_requiring_review(
        self,
        limit: int = 100,
    ) -> list[Hand]:
        """Get hands that require manual review."""
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(Hand)
                .where(Hand.requires_review == True)  # noqa: E712
                .order_by(Hand.started_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def update_hand_duration(
        self,
        hand_id: int,
        ended_at: datetime,
        duration_seconds: int,
    ) -> None:
        """Update hand end time and duration."""
        async with self.db_manager.session() as session:
            result = await session.execute(select(Hand).where(Hand.id == hand_id))
            hand = result.scalar_one_or_none()
            if hand:
                hand.ended_at = ended_at
                hand.duration_seconds = duration_seconds
                logger.debug(f"Updated hand {hand_id} duration to {duration_seconds}s")

    async def get_manual_marks_for_table(
        self,
        table_id: str,
        since: datetime | None = None,
    ) -> list[ManualMark]:
        """Get manual marks for a table, optionally filtered by time."""
        async with self.db_manager.session() as session:
            query = select(ManualMark).where(ManualMark.table_id == table_id)
            if since:
                query = query.where(ManualMark.marked_at >= since)
            query = query.order_by(ManualMark.marked_at.desc())

            result = await session.execute(query)
            return list(result.scalars().all())
