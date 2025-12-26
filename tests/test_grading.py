"""Tests for hand grading module."""

import pytest

from src.grading.grader import GradeResult, HandGrader
from src.models.hand import HandRank


class TestHandGrader:
    """Test cases for HandGrader."""

    def setup_method(self):
        """Set up test fixtures."""
        self.grader = HandGrader(
            playtime_threshold=120,
            board_combo_threshold=7,
        )

    def test_grade_a_all_conditions_met(self):
        """Test grade A when all 3 conditions are met."""
        result = self.grader.grade(
            hand_rank=HandRank.ROYAL_FLUSH,  # Premium hand
            duration_seconds=150,  # Long playtime
            board_rank_value=3,  # Premium board combo
        )

        assert result.grade == "A"
        assert result.has_premium_hand is True
        assert result.has_long_playtime is True
        assert result.has_premium_board_combo is True
        assert result.conditions_met == 3
        assert result.broadcast_eligible is True

    def test_grade_b_two_conditions_met(self):
        """Test grade B when 2 conditions are met."""
        result = self.grader.grade(
            hand_rank=HandRank.FULL_HOUSE,  # Premium hand
            duration_seconds=150,  # Long playtime
            board_rank_value=8,  # Not premium board
        )

        assert result.grade == "B"
        assert result.has_premium_hand is True
        assert result.has_long_playtime is True
        assert result.has_premium_board_combo is False
        assert result.conditions_met == 2
        assert result.broadcast_eligible is True

    def test_grade_c_one_condition_met(self):
        """Test grade C when only 1 condition is met."""
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,  # Not premium
            duration_seconds=150,  # Long playtime only
            board_rank_value=10,  # Not premium board
        )

        assert result.grade == "C"
        assert result.has_premium_hand is False
        assert result.has_long_playtime is True
        assert result.has_premium_board_combo is False
        assert result.conditions_met == 1
        assert result.broadcast_eligible is False

    def test_grade_c_no_conditions_met(self):
        """Test grade C when no conditions are met."""
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,  # Not premium
            duration_seconds=60,  # Short playtime
            board_rank_value=10,  # Not premium board
        )

        assert result.grade == "C"
        assert result.conditions_met == 0
        assert result.broadcast_eligible is False

    def test_premium_hand_detection(self):
        """Test that premium hands are correctly identified."""
        premium_ranks = [
            HandRank.ROYAL_FLUSH,
            HandRank.STRAIGHT_FLUSH,
            HandRank.FOUR_OF_A_KIND,
            HandRank.FULL_HOUSE,
        ]

        for rank in premium_ranks:
            result = self.grader.grade(hand_rank=rank, duration_seconds=60)
            assert result.has_premium_hand is True, f"{rank.name} should be premium"

        non_premium_ranks = [
            HandRank.FLUSH,
            HandRank.STRAIGHT,
            HandRank.THREE_OF_A_KIND,
            HandRank.TWO_PAIR,
            HandRank.ONE_PAIR,
            HandRank.HIGH_CARD,
        ]

        for rank in non_premium_ranks:
            result = self.grader.grade(hand_rank=rank, duration_seconds=60)
            assert result.has_premium_hand is False, f"{rank.name} should not be premium"

    def test_long_playtime_detection(self):
        """Test that long playtime is correctly identified."""
        # Exactly at threshold
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=120,
        )
        assert result.has_long_playtime is True

        # Below threshold
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=119,
        )
        assert result.has_long_playtime is False

        # Above threshold
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=180,
        )
        assert result.has_long_playtime is True

    def test_board_combo_detection(self):
        """Test that premium board combo is correctly identified."""
        # Three of a kind (rank 7) - should be premium
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=60,
            board_rank_value=7,
        )
        assert result.has_premium_board_combo is True

        # Two pair (rank 8) - should not be premium
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=60,
            board_rank_value=8,
        )
        assert result.has_premium_board_combo is False

        # No board rank provided
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=60,
            board_rank_value=None,
        )
        assert result.has_premium_board_combo is False

    def test_edit_offset_for_premium_hands(self):
        """Test that premium hands get offset 0."""
        result = self.grader.grade(
            hand_rank=HandRank.ROYAL_FLUSH,
            duration_seconds=180,
        )
        assert result.suggested_edit_offset == 0

    def test_edit_offset_for_long_hands(self):
        """Test that long non-premium hands skip early action."""
        result = self.grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=200,
        )
        # Should skip about 40% of the hand
        assert result.suggested_edit_offset > 60

    def test_broadcast_eligibility(self):
        """Test broadcast eligibility based on grade."""
        assert self.grader.is_broadcast_eligible("A") is True
        assert self.grader.is_broadcast_eligible("B") is True
        assert self.grader.is_broadcast_eligible("C") is False

    def test_grade_description(self):
        """Test grade descriptions."""
        assert "All conditions" in self.grader.get_grade_description("A")
        assert "Broadcast eligible" in self.grader.get_grade_description("B")
        assert "Archive" in self.grader.get_grade_description("C")

    def test_custom_thresholds(self):
        """Test with custom threshold values."""
        custom_grader = HandGrader(
            playtime_threshold=60,  # Lower threshold
            board_combo_threshold=5,  # Stricter board combo
        )

        # Should now count 60 seconds as long
        result = custom_grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=60,
        )
        assert result.has_long_playtime is True

        # Board combo with rank 6 should not be premium with threshold 5
        result = custom_grader.grade(
            hand_rank=HandRank.HIGH_CARD,
            duration_seconds=60,
            board_rank_value=6,
        )
        assert result.has_premium_board_combo is False
