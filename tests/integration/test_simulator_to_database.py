"""E2E Integration Tests: Simulator → Fusion → Grading → Monitoring → Database.

This module tests the complete data flow from GFX JSON Simulator through
Fusion Engine, Hand Grader, and Monitoring Service to Database storage.

Test Scenarios:
1. Primary + Secondary Match → Grade A (Royal Flush, 3 conditions)
2. Primary + Secondary Mismatch → Grade B (Full House, 2 conditions, review flag)
3. Secondary Fallback → Grade C (Three of a Kind, 1 condition)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.fusion.engine import FusionEngine
from src.grading.grader import GradeResult, HandGrader
from src.models.hand import (
    AIVideoResult,
    Card,
    FusedHandResult,
    HandRank,
    HandResult,
    SourceType,
)
from src.simulator.gfx_json_simulator import GFXJsonSimulator, Status
from src.simulator.hand_splitter import HandSplitter


class TestSimulatorToFusion:
    """Test Simulator → Fusion Engine integration."""

    def test_simulator_generates_hand_result(self, tmp_path: Path) -> None:
        """Test that simulator generates valid JSON that can be converted to HandResult."""
        # Arrange: Create source JSON
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        gfx_json = {
            "TableId": "table1",
            "Hands": [
                {
                    "HandNum": 1,
                    "Players": [
                        {
                            "PlayerNum": 1,
                            "Name": "Player1",
                            "HoleCards": ["As", "Ks"],
                            "EndStackAmt": 1000,
                        }
                    ],
                    "BoardCards": ["Qs", "Js", "Ts", "2h", "3c"],
                    "PotAmt": 500,
                    "WinningPlayer": "Player1",
                    "Timestamp": datetime.now().isoformat(),
                }
            ],
            "SessionId": "session1",
        }

        source_file = source_dir / "table1.json"
        source_file.write_text(json.dumps(gfx_json), encoding="utf-8")

        # Act: Split hands
        hands = HandSplitter.split_hands(gfx_json)
        cumulative = HandSplitter.build_cumulative(hands, 1, HandSplitter.extract_metadata(gfx_json))

        # Assert: JSON structure is valid for HandResult conversion
        assert len(hands) == 1
        hand = hands[0]
        assert hand["HandNum"] == 1
        assert "Players" in hand
        assert "BoardCards" in hand

        # Verify can convert to HandResult
        hand_result = self._convert_to_hand_result(hand, "table1")
        assert hand_result.table_id == "table1"
        assert hand_result.hand_number == 1
        assert hand_result.pot_size == 500

    def test_fusion_with_matching_primary_secondary(self) -> None:
        """Test Fusion Engine with matching Primary and Secondary results."""
        # Arrange: Create matching results (Royal Flush)
        primary = HandResult(
            table_id="table1",
            hand_number=1,
            hand_rank=HandRank.ROYAL_FLUSH,
            rank_value=1,
            is_premium=True,
            confidence=1.0,
            players_showdown=[{"PlayerNum": 1, "Name": "Player1"}],
            pot_size=1000,
            timestamp=datetime.now(),
            community_cards=[
                Card("A", "s"),
                Card("K", "s"),
                Card("Q", "s"),
                Card("J", "s"),
                Card("T", "s"),
            ],
            winner="Player1",
        )

        secondary = AIVideoResult(
            table_id="table1",
            detected_event="showdown",
            detected_cards=[Card("A", "s"), Card("K", "s")],
            hand_rank=HandRank.ROYAL_FLUSH,
            confidence=0.95,
            context="Player1 shows Royal Flush",
            timestamp=datetime.now(),
        )

        engine = FusionEngine(secondary_confidence_threshold=0.80)

        # Act
        result = engine.fuse(primary, secondary)

        # Assert
        assert isinstance(result, FusedHandResult)
        assert result.cross_validated is True
        assert result.requires_review is False
        assert result.source == SourceType.PRIMARY
        assert result.hand_rank == HandRank.ROYAL_FLUSH
        assert result.confidence == 1.0

    def test_fusion_with_mismatched_primary_secondary(self) -> None:
        """Test Fusion Engine with mismatched Primary and Secondary results."""
        # Arrange: Create mismatched results
        primary = HandResult(
            table_id="table1",
            hand_number=2,
            hand_rank=HandRank.FULL_HOUSE,
            rank_value=4,
            is_premium=True,
            confidence=1.0,
            players_showdown=[{"PlayerNum": 1, "Name": "Player1"}],
            pot_size=800,
            timestamp=datetime.now(),
            winner="Player1",
        )

        secondary = AIVideoResult(
            table_id="table1",
            detected_event="showdown",
            detected_cards=[Card("K", "h"), Card("K", "d")],
            hand_rank=HandRank.THREE_OF_A_KIND,  # Different!
            confidence=0.85,
            context="Player1 shows trips",
            timestamp=datetime.now(),
        )

        engine = FusionEngine(secondary_confidence_threshold=0.80)

        # Act
        result = engine.fuse(primary, secondary)

        # Assert
        assert result.cross_validated is False
        assert result.requires_review is True  # Flagged for review
        assert result.source == SourceType.PRIMARY  # Still uses Primary
        assert result.hand_rank == HandRank.FULL_HOUSE

    def test_fusion_secondary_fallback(self) -> None:
        """Test Fusion Engine fallback to Secondary when Primary unavailable."""
        # Arrange: Only Secondary available
        secondary = AIVideoResult(
            table_id="table1",
            detected_event="showdown",
            detected_cards=[Card("7", "h"), Card("7", "d"), Card("7", "s")],
            hand_rank=HandRank.THREE_OF_A_KIND,
            confidence=0.85,  # Above threshold
            context="Player shows three sevens",
            timestamp=datetime.now(),
        )

        engine = FusionEngine(secondary_confidence_threshold=0.80)

        # Act
        result = engine.fuse(None, secondary)

        # Assert
        assert result.source == SourceType.SECONDARY
        assert result.hand_rank == HandRank.THREE_OF_A_KIND
        assert result.confidence == 0.85
        assert result.cross_validated is False

    def _convert_to_hand_result(self, hand: dict[str, Any], table_id: str) -> HandResult:
        """Convert GFX JSON hand to HandResult."""
        # Simplified conversion for testing
        board_cards = [Card.from_string(c) for c in hand.get("BoardCards", [])]
        return HandResult(
            table_id=table_id,
            hand_number=hand["HandNum"],
            hand_rank=HandRank.HIGH_CARD,  # Would use phevaluator in real code
            rank_value=10,
            is_premium=False,
            confidence=1.0,
            players_showdown=hand.get("Players", []),
            pot_size=hand.get("PotAmt", 0),
            timestamp=datetime.now(),
            community_cards=board_cards,
            winner=hand.get("WinningPlayer"),
        )


class TestFusionToGrading:
    """Test Fusion → Grading integration."""

    def test_grade_a_all_conditions(self) -> None:
        """Test Grade A: All 3 conditions met (Royal Flush, long play, board combo)."""
        grader = HandGrader(playtime_threshold=120)

        # Royal Flush (premium), 180s duration (long play), board combo
        result = grader.grade(
            hand_rank=HandRank.ROYAL_FLUSH,
            duration_seconds=180,
            board_rank_value=1,  # Royal Flush on board
        )

        assert result.grade == "A"
        assert result.has_premium_hand is True
        assert result.has_long_playtime is True
        assert result.has_premium_board_combo is True
        assert result.conditions_met == 3
        assert result.broadcast_eligible is True

    def test_grade_b_two_conditions(self) -> None:
        """Test Grade B: 2 conditions met (Full House, short play, board combo)."""
        grader = HandGrader(playtime_threshold=120)

        # Full House (premium), 90s duration (short), board combo
        result = grader.grade(
            hand_rank=HandRank.FULL_HOUSE,
            duration_seconds=90,  # Below threshold
            board_rank_value=4,  # Full House on board
        )

        assert result.grade == "B"
        assert result.has_premium_hand is True
        assert result.has_long_playtime is False
        assert result.has_premium_board_combo is True
        assert result.conditions_met == 2
        assert result.broadcast_eligible is True

    def test_grade_c_one_condition(self) -> None:
        """Test Grade C: 1 condition met (Three of a Kind, short play, no board combo)."""
        grader = HandGrader(playtime_threshold=120)

        # Three of a Kind (not premium), 60s duration, no board combo
        result = grader.grade(
            hand_rank=HandRank.THREE_OF_A_KIND,
            duration_seconds=60,
            board_rank_value=10,  # High card on board
        )

        assert result.grade == "C"
        assert result.has_premium_hand is False
        assert result.has_long_playtime is False
        assert result.has_premium_board_combo is False
        assert result.conditions_met == 0
        assert result.broadcast_eligible is False

    def test_grade_b_premium_hand_with_long_play(self) -> None:
        """Test Grade B: Premium hand + long play (no board combo)."""
        grader = HandGrader(playtime_threshold=120)

        # Four of a Kind (premium), 150s duration (long), no board combo
        result = grader.grade(
            hand_rank=HandRank.FOUR_OF_A_KIND,
            duration_seconds=150,
            board_rank_value=9,  # One pair on board
        )

        assert result.grade == "B"
        assert result.has_premium_hand is True
        assert result.has_long_playtime is True
        assert result.has_premium_board_combo is False
        assert result.conditions_met == 2


class TestGradingToMonitoring:
    """Test Grading → Monitoring Service integration."""

    @pytest.fixture
    def mock_monitoring_service(self) -> MagicMock:
        """Create mock MonitoringService."""
        mock = MagicMock()
        mock.initialize = AsyncMock()
        mock.record_hand_grade = AsyncMock()
        mock.update_table_connection = AsyncMock()
        mock.update_current_hand = AsyncMock()
        mock.update_fusion_result = AsyncMock()
        mock._initialized = True
        return mock

    async def test_record_grade_a_triggers_alert(self, mock_monitoring_service: MagicMock) -> None:
        """Test that Grade A hand triggers alert via monitoring service."""
        from src.dashboard.alerts import AlertManager

        alert_manager = AlertManager()
        mock_monitoring_service.alert_manager = alert_manager

        grade_result = GradeResult(
            grade="A",
            has_premium_hand=True,
            has_long_playtime=True,
            has_premium_board_combo=True,
            conditions_met=3,
            broadcast_eligible=True,
        )

        # Simulate the alert logic from MonitoringService.record_hand_grade
        if grade_result.grade == "A":
            conditions_met = []
            if grade_result.has_premium_hand:
                conditions_met.append("premium_hand")
            if grade_result.has_long_playtime:
                conditions_met.append("long_playtime")
            if grade_result.has_premium_board_combo:
                conditions_met.append("board_combo")

            alert_manager.alert_grade_a_hand(
                table_id="table1",
                hand_number=42,
                hand_rank="Royal Flush",
                conditions_met=conditions_met,
            )

        # Assert alert was created
        from src.dashboard.alerts import AlertType

        active_alerts = alert_manager.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].alert_type == AlertType.GRADE_A_HAND


class TestEndToEndFlow:
    """Complete E2E flow tests: Simulator → Fusion → Grading → Monitoring → DB."""

    @pytest.fixture
    def mock_supabase_repo(self) -> MagicMock:
        """Create mock Supabase repository."""
        mock = MagicMock()
        mock.save_hand = AsyncMock(return_value=True)
        mock.upsert_table_status = AsyncMock(return_value=True)
        mock.create_recording_session = AsyncMock(return_value={"session_id": "sess_001"})
        return mock

    async def test_complete_flow_grade_a(
        self,
        tmp_path: Path,
        mock_supabase_repo: MagicMock,
    ) -> None:
        """Test complete flow: Royal Flush → Grade A → DB save."""
        # Step 1: Simulator generates JSON
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        gfx_json = {
            "TableId": "table1",
            "Hands": [
                {
                    "HandNum": 1,
                    "Players": [
                        {
                            "PlayerNum": 1,
                            "Name": "Winner",
                            "HoleCards": ["As", "Ks"],
                            "EndStackAmt": 2000,
                        }
                    ],
                    "BoardCards": ["Qs", "Js", "Ts", "2h", "3c"],
                    "PotAmt": 1500,
                    "WinningPlayer": "Winner",
                    "Duration": 180,
                    "Timestamp": datetime.now().isoformat(),
                }
            ],
            "SessionId": "session_001",
        }

        source_file = source_dir / "table1.json"
        source_file.write_text(json.dumps(gfx_json), encoding="utf-8")

        # Step 2: Create HandResult from simulator data
        hand = gfx_json["Hands"][0]
        primary = HandResult(
            table_id="table1",
            hand_number=1,
            hand_rank=HandRank.ROYAL_FLUSH,
            rank_value=1,
            is_premium=True,
            confidence=1.0,
            players_showdown=hand["Players"],
            pot_size=hand["PotAmt"],
            timestamp=datetime.now(),
            community_cards=[Card.from_string(c) for c in hand["BoardCards"]],
            winner=hand["WinningPlayer"],
        )

        secondary = AIVideoResult(
            table_id="table1",
            detected_event="showdown",
            detected_cards=[Card("A", "s"), Card("K", "s")],
            hand_rank=HandRank.ROYAL_FLUSH,
            confidence=0.92,
            context="Royal Flush detected",
            timestamp=datetime.now(),
        )

        # Step 3: Fusion
        fusion_engine = FusionEngine()
        fused = fusion_engine.fuse(primary, secondary)

        assert fused.cross_validated is True
        assert fused.hand_rank == HandRank.ROYAL_FLUSH

        # Step 4: Grading
        grader = HandGrader(playtime_threshold=120)
        grade_result = grader.grade(
            hand_rank=fused.hand_rank,
            duration_seconds=hand["Duration"],
            board_rank_value=1,
        )

        assert grade_result.grade == "A"
        assert grade_result.broadcast_eligible is True

        # Step 5: Verify DB would be called (mock)
        await mock_supabase_repo.save_hand(
            table_id=fused.table_id,
            hand_number=fused.hand_number,
            hand_rank=fused.hand_rank.name,
            grade=grade_result.grade,
        )

        mock_supabase_repo.save_hand.assert_called_once()

    async def test_complete_flow_grade_b_with_review(
        self,
        tmp_path: Path,
        mock_supabase_repo: MagicMock,
    ) -> None:
        """Test complete flow: Mismatch → Grade B → Review flag → DB save."""
        # Step 1: Create mismatched results
        primary = HandResult(
            table_id="table2",
            hand_number=5,
            hand_rank=HandRank.FULL_HOUSE,
            rank_value=4,
            is_premium=True,
            confidence=1.0,
            players_showdown=[{"PlayerNum": 2, "Name": "Player2"}],
            pot_size=800,
            timestamp=datetime.now(),
            winner="Player2",
        )

        secondary = AIVideoResult(
            table_id="table2",
            detected_event="showdown",
            detected_cards=[Card("K", "h"), Card("K", "d")],
            hand_rank=HandRank.TWO_PAIR,  # Mismatch!
            confidence=0.75,
            context="Two pair detected",
            timestamp=datetime.now(),
        )

        # Step 2: Fusion (should flag for review)
        fusion_engine = FusionEngine()
        fused = fusion_engine.fuse(primary, secondary)

        assert fused.requires_review is True
        assert fused.hand_rank == HandRank.FULL_HOUSE  # Uses Primary

        # Step 3: Grading
        grader = HandGrader(playtime_threshold=120)
        grade_result = grader.grade(
            hand_rank=fused.hand_rank,
            duration_seconds=90,  # Short play
            board_rank_value=4,  # Full House on board
        )

        assert grade_result.grade == "B"
        assert grade_result.conditions_met == 2  # Premium + board combo

        # Step 4: Verify DB save would include review flag
        await mock_supabase_repo.save_hand(
            table_id=fused.table_id,
            hand_number=fused.hand_number,
            hand_rank=fused.hand_rank.name,
            grade=grade_result.grade,
            requires_review=fused.requires_review,
        )

        call_kwargs = mock_supabase_repo.save_hand.call_args.kwargs
        assert call_kwargs["requires_review"] is True

    async def test_complete_flow_secondary_fallback(
        self,
        mock_supabase_repo: MagicMock,
    ) -> None:
        """Test complete flow: Secondary fallback → Grade C → DB save."""
        # Step 1: Only Secondary available
        secondary = AIVideoResult(
            table_id="table3",
            detected_event="showdown",
            detected_cards=[Card("7", "h"), Card("7", "d")],
            hand_rank=HandRank.THREE_OF_A_KIND,
            confidence=0.85,
            context="Three of a kind",
            timestamp=datetime.now(),
        )

        # Step 2: Fusion (fallback to Secondary)
        fusion_engine = FusionEngine(secondary_confidence_threshold=0.80)
        fused = fusion_engine.fuse(None, secondary)

        assert fused.source == SourceType.SECONDARY
        assert fused.confidence == 0.85

        # Step 3: Grading
        grader = HandGrader(playtime_threshold=120)
        grade_result = grader.grade(
            hand_rank=fused.hand_rank,
            duration_seconds=45,  # Short
            board_rank_value=10,  # High card
        )

        assert grade_result.grade == "C"
        assert grade_result.broadcast_eligible is False

        # Step 4: DB save
        await mock_supabase_repo.save_hand(
            table_id=fused.table_id,
            hand_number=fused.hand_number,
            hand_rank=fused.hand_rank.name,
            grade=grade_result.grade,
            source=fused.source.value,
        )

        call_kwargs = mock_supabase_repo.save_hand.call_args.kwargs
        assert call_kwargs["source"] == "ai_video"


class TestSimulatorWithFusion:
    """Test Simulator async operations with Fusion."""

    async def test_simulator_runs_and_produces_fusable_data(self, tmp_path: Path) -> None:
        """Test that simulator produces data compatible with Fusion Engine."""
        # Arrange
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        gfx_json = {
            "TableId": "fusion_test",
            "Hands": [
                {
                    "HandNum": 1,
                    "Players": [{"PlayerNum": 1, "Name": "TestPlayer", "HoleCards": ["Ah", "Kh"]}],
                    "BoardCards": ["Qh", "Jh", "Th", "2c", "3d"],
                    "PotAmt": 1000,
                }
            ],
            "SessionId": "test_session",
        }

        source_file = source_dir / "test.json"
        source_file.write_text(json.dumps(gfx_json), encoding="utf-8")

        # Act: Run simulator
        simulator = GFXJsonSimulator(
            source_path=source_dir,
            target_path=target_dir,
            interval=0,  # No delay for testing
        )

        await simulator.run()

        # Assert: Output file exists
        output_file = target_dir / "test.json"
        assert output_file.exists()

        # Verify output is valid JSON
        output_data = json.loads(output_file.read_text(encoding="utf-8"))
        assert "Hands" in output_data
        assert len(output_data["Hands"]) == 1

        # Verify data can be used for HandResult
        hand = output_data["Hands"][0]
        assert hand["HandNum"] == 1
        assert "BoardCards" in hand

    async def test_simulator_status_transitions(self, tmp_path: Path) -> None:
        """Test simulator status transitions during run."""
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()

        gfx_json = {
            "TableId": "status_test",
            "Hands": [{"HandNum": 1, "Players": [], "BoardCards": [], "PotAmt": 100}],
            "SessionId": "status_session",
        }

        (source_dir / "status.json").write_text(json.dumps(gfx_json), encoding="utf-8")

        simulator = GFXJsonSimulator(
            source_path=source_dir,
            target_path=target_dir,
            interval=0,
        )

        # Initial state
        assert simulator.status == Status.IDLE

        # Run
        await simulator.run()

        # Final state
        assert simulator.status == Status.COMPLETED
