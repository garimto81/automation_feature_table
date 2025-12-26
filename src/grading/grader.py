"""Hand grading for A/B/C classification."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.models.hand import HandRank

if TYPE_CHECKING:
    from src.config.settings import GradingSettings
    from src.models.hand import FusedHandResult

logger = logging.getLogger(__name__)


@dataclass
class GradeResult:
    """Result of hand grading."""

    grade: str  # 'A', 'B', 'C'
    has_premium_hand: bool
    has_long_playtime: bool
    has_premium_board_combo: bool
    conditions_met: int
    broadcast_eligible: bool
    suggested_edit_offset: int | None = None
    edit_confidence: float = 0.0


class HandGrader:
    """Poker hand grader based on 3 conditions.

    Grading Criteria (CLAUDE.md):
    =============================
    Conditions (2+ required for broadcast eligibility):
    1. Premium hand: Royal Flush, Straight Flush, Four of a Kind, Full House
    2. Long playtime: Hand duration exceeds threshold (default 120s)
    3. Premium board combo: Three of a Kind or better (rank value <= 7)

    Grades:
    - A: All 3 conditions met
    - B: 2 conditions met (broadcast eligible)
    - C: 1 or 0 conditions met (not broadcast eligible)
    """

    # Premium hands: Full House or better (HandRank value 1-4)
    PREMIUM_RANK_THRESHOLD = 4

    # Board combo: Three of a Kind or better (HandRank value 1-7)
    BOARD_COMBO_RANK_THRESHOLD = 7

    # Default playtime threshold
    DEFAULT_PLAYTIME_THRESHOLD = 120

    def __init__(
        self,
        playtime_threshold: int = DEFAULT_PLAYTIME_THRESHOLD,
        board_combo_threshold: int = BOARD_COMBO_RANK_THRESHOLD,
    ):
        """Initialize grader.

        Args:
            playtime_threshold: Minimum playtime in seconds for condition 2
            board_combo_threshold: Maximum rank value for premium board combo
        """
        self.playtime_threshold = playtime_threshold
        self.board_combo_threshold = board_combo_threshold

    @classmethod
    def from_settings(cls, settings: "GradingSettings") -> "HandGrader":
        """Create grader from settings."""
        return cls(
            playtime_threshold=settings.playtime_threshold,
            board_combo_threshold=settings.board_combo_threshold,
        )

    def grade(
        self,
        hand_rank: HandRank,
        duration_seconds: int,
        board_rank_value: int | None = None,
    ) -> GradeResult:
        """Grade a poker hand.

        Args:
            hand_rank: The player's final hand rank
            duration_seconds: Hand play duration in seconds
            board_rank_value: Best possible board-only combination rank value (optional)

        Returns:
            GradeResult with grade and criteria details
        """
        # Condition 1: Premium hand (Full House or better)
        has_premium_hand = hand_rank.value <= self.PREMIUM_RANK_THRESHOLD

        # Condition 2: Long playtime
        has_long_playtime = duration_seconds >= self.playtime_threshold

        # Condition 3: Premium board combo
        has_premium_board_combo = False
        if board_rank_value is not None:
            # Lower rank_value = better hand
            has_premium_board_combo = board_rank_value <= self.board_combo_threshold

        # Count conditions met
        conditions = [has_premium_hand, has_long_playtime, has_premium_board_combo]
        conditions_met = sum(conditions)

        # Determine grade
        if conditions_met >= 3:
            grade = "A"
        elif conditions_met >= 2:
            grade = "B"
        else:
            grade = "C"

        # Broadcast eligibility (B or better)
        broadcast_eligible = grade in ("A", "B")

        # Estimate edit point offset
        suggested_offset = self._estimate_edit_offset(
            hand_rank, duration_seconds, has_premium_hand
        )

        result = GradeResult(
            grade=grade,
            has_premium_hand=has_premium_hand,
            has_long_playtime=has_long_playtime,
            has_premium_board_combo=has_premium_board_combo,
            conditions_met=conditions_met,
            broadcast_eligible=broadcast_eligible,
            suggested_edit_offset=suggested_offset,
            edit_confidence=0.8 if broadcast_eligible else 0.4,
        )

        logger.info(
            f"Graded hand: {grade} (conditions: {conditions_met}/3, "
            f"premium={has_premium_hand}, long_play={has_long_playtime}, "
            f"board_combo={has_premium_board_combo}, duration={duration_seconds}s)"
        )

        return result

    def grade_fused_result(
        self,
        result: "FusedHandResult",
        duration_seconds: int,
        board_rank_value: int | None = None,
    ) -> GradeResult:
        """Grade a FusedHandResult.

        Args:
            result: FusedHandResult from fusion engine
            duration_seconds: Hand play duration
            board_rank_value: Optional board-only rank value

        Returns:
            GradeResult
        """
        return self.grade(
            hand_rank=result.hand_rank,
            duration_seconds=duration_seconds,
            board_rank_value=board_rank_value,
        )

    def _estimate_edit_offset(
        self,
        hand_rank: HandRank,
        duration_seconds: int,
        is_premium: bool,
    ) -> int:
        """Estimate optimal edit start offset from hand start.

        Based on broadcast patterns:
        - Premium hands: Start earlier to show buildup
        - Standard hands: Start at flop or later
        - Very long hands: Skip early action

        Args:
            hand_rank: Hand rank
            duration_seconds: Total hand duration
            is_premium: Whether this is a premium hand

        Returns:
            Suggested offset in seconds from hand start
        """
        if is_premium:
            # For premium hands, start from the beginning to show buildup
            return 0

        if duration_seconds > 180:
            # Very long hands: Start around the turn
            # Skip first ~40% of the hand
            return max(0, int(duration_seconds * 0.4))

        if duration_seconds > 60:
            # Standard hands: Start at flop (roughly 1/3 into hand)
            return min(30, duration_seconds // 3)

        # Short hands: Start from beginning
        return 0

    def get_grade_description(self, grade: str) -> str:
        """Get human-readable description for a grade."""
        descriptions = {
            "A": "Highest priority - All conditions met",
            "B": "Broadcast eligible - 2 conditions met",
            "C": "Archive only - Insufficient conditions",
        }
        return descriptions.get(grade, "Unknown grade")

    def is_broadcast_eligible(self, grade: str) -> bool:
        """Check if a grade is eligible for broadcast."""
        return grade in ("A", "B")
