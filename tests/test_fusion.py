"""Tests for fusion engine."""

from datetime import datetime

import pytest

from src.fusion.engine import FusionEngine, MultiTableFusionEngine
from src.models.hand import AIVideoResult, Card, HandRank, HandResult, SourceType


@pytest.fixture
def fusion_engine():
    """Create a FusionEngine instance."""
    return FusionEngine(secondary_confidence_threshold=0.80)


@pytest.fixture
def sample_primary_result():
    """Create a sample Primary result."""
    return HandResult(
        table_id="table_1",
        hand_number=123,
        hand_rank=HandRank.FULL_HOUSE,
        rank_value=200,
        is_premium=True,
        confidence=1.0,
        players_showdown=[{"player": "Player A", "rank_name": "Full House"}],
        pot_size=5000,
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_secondary_result():
    """Create a sample Secondary result."""
    return AIVideoResult(
        table_id="table_1",
        detected_event="showdown",
        detected_cards=[Card.from_string("Ah"), Card.from_string("Kd")],
        hand_rank=HandRank.FULL_HOUSE,
        confidence=0.92,
        context="Player A shows full house",
        timestamp=datetime.now(),
    )


class TestFusionEngine:
    """Test FusionEngine."""

    def test_primary_only(self, fusion_engine, sample_primary_result):
        """Test Case 1: Primary available, no secondary."""
        result = fusion_engine.fuse(sample_primary_result, None)

        assert result.source == SourceType.PRIMARY
        assert result.confidence == 1.0
        assert result.cross_validated is True
        assert result.requires_review is False
        assert result.hand_rank == HandRank.FULL_HOUSE

    def test_primary_with_matching_secondary(
        self, fusion_engine, sample_primary_result, sample_secondary_result
    ):
        """Test Case 1: Primary and Secondary match."""
        result = fusion_engine.fuse(sample_primary_result, sample_secondary_result)

        assert result.source == SourceType.PRIMARY
        assert result.cross_validated is True
        assert result.requires_review is False

    def test_primary_with_mismatching_secondary(
        self, fusion_engine, sample_primary_result
    ):
        """Test Case 2: Primary and Secondary differ."""
        mismatched_secondary = AIVideoResult(
            table_id="table_1",
            detected_event="showdown",
            detected_cards=[],
            hand_rank=HandRank.FLUSH,  # Different from primary's FULL_HOUSE
            confidence=0.85,
            context="Detected flush",
            timestamp=datetime.now(),
        )

        result = fusion_engine.fuse(sample_primary_result, mismatched_secondary)

        assert result.source == SourceType.PRIMARY
        assert result.cross_validated is False
        assert result.requires_review is True

    def test_secondary_only_high_confidence(self, fusion_engine, sample_secondary_result):
        """Test Case 3: Secondary only with high confidence."""
        result = fusion_engine.fuse(None, sample_secondary_result)

        assert result.source == SourceType.SECONDARY
        assert result.confidence == 0.92
        assert result.requires_review is True

    def test_secondary_only_low_confidence(self, fusion_engine):
        """Test Case 3: Secondary only with low confidence."""
        low_confidence_secondary = AIVideoResult(
            table_id="table_1",
            detected_event="action",
            detected_cards=[],
            hand_rank=HandRank.FLUSH,
            confidence=0.50,  # Below threshold
            context="Uncertain detection",
            timestamp=datetime.now(),
        )

        result = fusion_engine.fuse(None, low_confidence_secondary)

        assert result.source == SourceType.MANUAL
        assert result.requires_review is True

    def test_neither_available(self, fusion_engine):
        """Test Case 4: Neither Primary nor Secondary available."""
        result = fusion_engine.fuse(None, None)

        assert result.source == SourceType.MANUAL
        assert result.confidence == 0.0
        assert result.requires_review is True

    def test_stats_tracking(self, fusion_engine, sample_primary_result, sample_secondary_result):
        """Test that statistics are tracked correctly."""
        # Case 1: Primary with matching secondary
        fusion_engine.fuse(sample_primary_result, sample_secondary_result)

        # Case 2: Primary with mismatched secondary
        mismatched = AIVideoResult(
            table_id="table_1",
            detected_event="showdown",
            detected_cards=[],
            hand_rank=HandRank.STRAIGHT,
            confidence=0.90,
            context="Different hand",
            timestamp=datetime.now(),
        )
        fusion_engine.fuse(sample_primary_result, mismatched)

        stats = fusion_engine.get_stats()

        assert stats["total"] == 2
        assert stats["cross_validated"] == 1
        assert stats["review_flagged"] == 1


class TestMultiTableFusionEngine:
    """Test MultiTableFusionEngine."""

    def test_multiple_tables(self, sample_primary_result, sample_secondary_result):
        """Test handling multiple tables."""
        engine = MultiTableFusionEngine(
            table_ids=["table_1", "table_2", "table_3"],
            secondary_confidence_threshold=0.80,
        )

        # Fuse for table_1
        result1 = engine.fuse("table_1", sample_primary_result, sample_secondary_result)
        assert result1.table_id == "table_1"

        # Fuse for table_2 (no results)
        result2 = engine.fuse("table_2", None, None)
        assert result2.source == SourceType.MANUAL

        # Check stats
        all_stats = engine.get_all_stats()
        assert "table_1" in all_stats
        assert "table_2" in all_stats

    def test_aggregate_stats(self, sample_primary_result):
        """Test aggregate statistics across tables."""
        engine = MultiTableFusionEngine(
            table_ids=["table_1", "table_2"],
            secondary_confidence_threshold=0.80,
        )

        # Add results for both tables
        engine.fuse("table_1", sample_primary_result, None)
        engine.fuse("table_2", sample_primary_result, None)

        aggregate = engine.get_aggregate_stats()

        assert aggregate["total"] == 2
        assert aggregate["cross_validated"] == 2  # Both had no secondary = validated
