"""SQLAlchemy ORM models for poker hand data."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Hand(Base):
    """Poker hand data from Primary/Secondary sources."""

    __tablename__ = "hands"
    __table_args__ = (UniqueConstraint("table_id", "hand_number", name="uq_table_hand"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    hand_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Card data (JSONB)
    community_cards: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    players_data: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    # Hand classification
    hand_rank: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    rank_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)

    # Data source info
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    secondary_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cross_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # Game metadata
    pot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    recordings: Mapped[list["Recording"]] = relationship(
        "Recording", back_populates="hand", cascade="all, delete-orphan"
    )
    grade: Mapped[Optional["Grade"]] = relationship(
        "Grade", back_populates="hand", uselist=False, cascade="all, delete-orphan"
    )
    manual_marks: Mapped[list["ManualMark"]] = relationship(
        "ManualMark", back_populates="hand"
    )


class Recording(Base):
    """Recording file information linked to a hand."""

    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hands.id", ondelete="CASCADE"), index=True
    )

    # File info
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Recording timing
    recording_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    recording_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # vMix metadata
    vmix_input_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vmix_recording_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="recording")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hand: Mapped["Hand"] = relationship("Hand", back_populates="recordings")


class Grade(Base):
    """Hand grading result (A/B/C classification)."""

    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("hands.id", ondelete="CASCADE"), unique=True
    )

    # Grade
    grade: Mapped[str] = mapped_column(String(1), nullable=False, index=True)

    # Grade conditions
    has_premium_hand: Mapped[bool] = mapped_column(Boolean, default=False)
    has_long_playtime: Mapped[bool] = mapped_column(Boolean, default=False)
    has_premium_board_combo: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions_met: Mapped[int] = mapped_column(Integer, nullable=False)

    # Broadcast eligibility
    broadcast_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Edit point suggestion
    suggested_edit_start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edit_start_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Grading info
    graded_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    graded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    hand: Mapped["Hand"] = relationship("Hand", back_populates="grade")


class ManualMark(Base):
    """Manual marking records for Plan B fallback."""

    __tablename__ = "manual_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Mark info
    marked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    mark_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Optional link to hand
    hand_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("hands.id", ondelete="SET NULL"), nullable=True
    )

    # Fallback context
    fallback_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    automation_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # User info
    marked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hand: Mapped[Optional["Hand"]] = relationship("Hand", back_populates="manual_marks")


# ============================================================================
# PRD-0008: 모니터링 대시보드 테이블
# ============================================================================


class TableStatus(Base):
    """Real-time table status for monitoring dashboard (PRD-0008)."""

    __tablename__ = "table_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)

    # Connection status
    primary_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    secondary_connected: Mapped[bool] = mapped_column(Boolean, default=False)

    # Current hand info
    current_hand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_hand_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hand_start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Fusion status
    last_fusion_result: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # validated, review, manual

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SystemHealthLog(Base):
    """System health log for monitoring dashboard (PRD-0008)."""

    __tablename__ = "system_health_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # connected, disconnected, error, warning

    # Metrics
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Message
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class RecordingSession(Base):
    """Recording session tracking for monitoring dashboard (PRD-0008)."""

    __tablename__ = "recording_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    table_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="recording"
    )  # recording, stopped, completed, error

    # Timing
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # File info
    file_size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # vMix info
    vmix_input: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
