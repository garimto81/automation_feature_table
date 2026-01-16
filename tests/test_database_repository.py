"""Tests for database repository - targeting 70%+ coverage."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.repository import HandRepository


class TestHandRepositorySaveHand:
    """Test save_hand method."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = MagicMock()
        manager.session = MagicMock()
        return manager

    @pytest.fixture
    def mock_fused_result(self):
        """Create mock fused hand result."""
        result = MagicMock()
        result.table_id = "table_1"
        result.hand_number = 123
        result.timestamp = datetime.now(UTC)
        result.rank_name = "Full House"
        result.is_premium = True
        result.source.value = "primary"
        result.confidence = 1.0
        result.cross_validated = True
        result.requires_review = False
        result.primary_result = MagicMock()
        result.primary_result.community_cards = ["Ah", "Kh", "Qh", "Jh", "Th"]
        result.primary_result.rank_value = 4
        result.players_data = [{"name": "Player 1", "cards": ["As", "Ks"]}]
        return result

    @pytest.fixture
    def mock_grade_result(self):
        """Create mock grade result."""
        grade = MagicMock()
        grade.grade = "A"
        grade.has_premium_hand = True
        grade.has_long_playtime = True
        grade.has_premium_board_combo = True
        grade.conditions_met = 3
        grade.broadcast_eligible = True
        grade.suggested_edit_offset = 10
        grade.edit_confidence = 0.95
        return grade

    async def test_save_hand_with_grade(
        self, mock_db_manager, mock_fused_result, mock_grade_result
    ):
        """Test saving hand with grade result."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.Hand") as mock_hand:
            with patch("src.database.repository.Grade") as mock_grade_class:
                mock_hand_instance = MagicMock()
                mock_hand_instance.id = 1
                mock_hand.return_value = mock_hand_instance

                hand = await repo.save_hand(mock_fused_result, mock_grade_result)

                # Should create hand and grade
                mock_hand.assert_called_once()
                mock_grade_class.assert_called_once()
                assert mock_session.add.call_count == 2

    async def test_save_hand_without_grade(
        self, mock_db_manager, mock_fused_result
    ):
        """Test saving hand without grade result."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.Hand") as mock_hand:
            mock_hand_instance = MagicMock()
            mock_hand_instance.id = 1
            mock_hand.return_value = mock_hand_instance

            hand = await repo.save_hand(mock_fused_result, None)

            # Should only create hand, not grade
            mock_hand.assert_called_once()
            assert mock_session.add.call_count == 1

    async def test_save_hand_no_community_cards(
        self, mock_db_manager, mock_fused_result
    ):
        """Test saving hand without community cards."""
        mock_fused_result.primary_result = None

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.Hand") as mock_hand:
            mock_hand_instance = MagicMock()
            mock_hand_instance.id = 1
            mock_hand.return_value = mock_hand_instance

            hand = await repo.save_hand(mock_fused_result, None)

            # Should handle None primary_result gracefully
            mock_hand.assert_called_once()


class TestHandRepositorySaveRecording:
    """Test save_recording method."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = MagicMock()
        manager.session = MagicMock()
        return manager

    async def test_save_recording_complete(self, mock_db_manager):
        """Test saving completed recording."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.Recording") as mock_recording:
            mock_rec_instance = MagicMock()
            mock_rec_instance.id = 1
            mock_recording.return_value = mock_rec_instance

            recording = await repo.save_recording(
                hand_id=1,
                file_path="/path/to/file.mp4",
                file_name="recording_123.mp4",
                recording_started_at=datetime.now(UTC),
                recording_ended_at=datetime.now(UTC),
                duration_seconds=120,
                vmix_input_number=3,
                status="completed",
            )

            mock_recording.assert_called_once()
            mock_session.add.assert_called_once()

    async def test_save_recording_in_progress(self, mock_db_manager):
        """Test saving in-progress recording."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.Recording") as mock_recording:
            mock_rec_instance = MagicMock()
            mock_recording.return_value = mock_rec_instance

            recording = await repo.save_recording(
                hand_id=1,
                file_path="/path/to/file.mp4",
                file_name="recording_123.mp4",
                recording_started_at=datetime.now(UTC),
                status="in_progress",
            )

            mock_recording.assert_called_once()


class TestHandRepositorySaveManualMark:
    """Test save_manual_mark method."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = MagicMock()
        manager.session = MagicMock()
        return manager

    async def test_save_manual_mark_full(self, mock_db_manager):
        """Test saving manual mark with all fields."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.ManualMark") as mock_mark:
            mock_mark_instance = MagicMock()
            mock_mark_instance.id = 1
            mock_mark.return_value = mock_mark_instance

            mark = await repo.save_manual_mark(
                table_id="table_1",
                mark_type="hand_end",
                marked_at=datetime.now(UTC),
                hand_id=123,
                fallback_reason="primary_timeout",
                automation_state={"reason": "timeout"},
                marked_by="operator_1",
            )

            mock_mark.assert_called_once()
            mock_session.add.assert_called_once()

    async def test_save_manual_mark_minimal(self, mock_db_manager):
        """Test saving manual mark with minimal fields."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        with patch("src.database.repository.ManualMark") as mock_mark:
            mock_mark_instance = MagicMock()
            mock_mark.return_value = mock_mark_instance

            mark = await repo.save_manual_mark(
                table_id="table_1",
                mark_type="hand_start",
                marked_at=datetime.now(UTC),
            )

            mock_mark.assert_called_once()


class TestHandRepositoryGetMethods:
    """Test get methods."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = MagicMock()
        manager.session = MagicMock()
        return manager

    async def test_get_hand_by_id_found(self, mock_db_manager):
        """Test getting hand by ID when found."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_hand = MagicMock()
        mock_hand.id = 1
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_hand)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        hand = await repo.get_hand_by_id(1)

        assert hand is not None
        assert hand.id == 1

    async def test_get_hand_by_id_not_found(self, mock_db_manager):
        """Test getting hand by ID when not found."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        hand = await repo.get_hand_by_id(999)

        assert hand is None

    async def test_get_hands_by_table(self, mock_db_manager):
        """Test getting hands by table ID."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_hands = [MagicMock(id=1), MagicMock(id=2)]
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_hands))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        hands = await repo.get_hands_by_table("table_1", limit=10, offset=0)

        assert len(hands) == 2

    async def test_get_broadcast_eligible_hands(self, mock_db_manager):
        """Test getting broadcast eligible hands."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_hands = [MagicMock(id=1), MagicMock(id=2)]
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_hands))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        hands = await repo.get_broadcast_eligible_hands(limit=50)

        assert len(hands) == 2

    async def test_get_hands_requiring_review(self, mock_db_manager):
        """Test getting hands requiring review."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_hands = [MagicMock(id=1)]
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_hands))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        hands = await repo.get_hands_requiring_review(limit=100)

        assert len(hands) == 1


class TestHandRepositoryUpdateMethods:
    """Test update methods."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = MagicMock()
        manager.session = MagicMock()
        return manager

    async def test_update_hand_duration_found(self, mock_db_manager):
        """Test updating hand duration when hand is found."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_hand = MagicMock()
        mock_hand.id = 1
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_hand)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        ended_at = datetime.now(UTC)
        await repo.update_hand_duration(1, ended_at, 180)

        assert mock_hand.ended_at == ended_at
        assert mock_hand.duration_seconds == 180

    async def test_update_hand_duration_not_found(self, mock_db_manager):
        """Test updating hand duration when hand is not found."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        # Should not raise error
        await repo.update_hand_duration(999, datetime.now(UTC), 180)


class TestHandRepositoryGetManualMarks:
    """Test get_manual_marks_for_table method."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        manager = MagicMock()
        manager.session = MagicMock()
        return manager

    async def test_get_manual_marks_without_since(self, mock_db_manager):
        """Test getting manual marks without time filter."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_marks = [MagicMock(id=1), MagicMock(id=2)]
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_marks))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        marks = await repo.get_manual_marks_for_table("table_1")

        assert len(marks) == 2

    async def test_get_manual_marks_with_since(self, mock_db_manager):
        """Test getting manual marks with time filter."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_marks = [MagicMock(id=1)]
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_marks))
        )
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_db_manager.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_db_manager.session.return_value.__aexit__ = AsyncMock()

        repo = HandRepository(mock_db_manager)

        since = datetime.now(UTC)
        marks = await repo.get_manual_marks_for_table("table_1", since=since)

        assert len(marks) == 1
