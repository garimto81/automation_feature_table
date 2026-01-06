"""Tests for JSON file watcher and parser."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.hand import HandRank
from src.primary.json_file_watcher import JSONFileWatcher
from src.primary.pokergfx_file_parser import PokerGFXFileParser


class TestPokerGFXFileParser:
    """Tests for PokerGFXFileParser class."""

    @pytest.fixture
    def parser(self) -> PokerGFXFileParser:
        """Create parser instance."""
        return PokerGFXFileParser()

    @pytest.fixture
    def sample_session_data(self) -> dict:
        """Sample PokerGFX session JSON data (PRD-0002 format)."""
        return {
            "CreatedDateTimeUTC": "2025-10-16T08:25:17.0907267Z",
            "EventTitle": "Feature Table Session",
            "Hands": [
                {
                    "HandNum": 1,
                    "GameVariant": "HOLDEM",
                    "GameClass": "FLOP",
                    "BetStructure": "NOLIMIT",
                    "Duration": "PT2M56S",
                    "StartDateTimeUTC": "2025-10-16T08:28:43.2539856Z",
                    "NumBoards": 1,
                    "RunItNumTimes": 1,
                    "Players": [
                        {
                            "PlayerNum": 1,
                            "Name": "Player A",
                            "LongName": "Player Alpha",
                            "StartStackAmt": 10000,
                            "EndStackAmt": 15000,
                            "CumulativeWinningsAmt": 5000,
                            "HoleCards": ["as", "kd"],
                            "SittingOut": False,
                            "EliminationRank": -1,
                        },
                        {
                            "PlayerNum": 2,
                            "Name": "Player B",
                            "LongName": "Player Beta",
                            "StartStackAmt": 10000,
                            "EndStackAmt": 5000,
                            "CumulativeWinningsAmt": -5000,
                            "HoleCards": ["qh", "qc"],
                            "SittingOut": False,
                            "EliminationRank": -1,
                        },
                    ],
                    "Events": [
                        {"EventType": "CALL", "PlayerNum": 1, "BetAmt": 100, "Pot": 200},
                        {"EventType": "RAISE", "PlayerNum": 2, "BetAmt": 300, "Pot": 500},
                        {"EventType": "CALL", "PlayerNum": 1, "BetAmt": 200, "Pot": 700},
                        {
                            "EventType": "BOARD CARD",
                            "BoardCards": ["ah", "kc", "7s"],
                            "BoardNum": 0,
                        },
                        {"EventType": "CHECK", "PlayerNum": 1, "Pot": 700},
                        {"EventType": "BET", "PlayerNum": 2, "BetAmt": 500, "Pot": 1200},
                        {"EventType": "CALL", "PlayerNum": 1, "BetAmt": 500, "Pot": 1700},
                        {
                            "EventType": "BOARD CARD",
                            "BoardCards": ["2d"],
                            "BoardNum": 0,
                        },
                        {
                            "EventType": "BOARD CARD",
                            "BoardCards": ["3h"],
                            "BoardNum": 0,
                        },
                        {"EventType": "SHOWDOWN"},
                    ],
                    "FlopDrawBlinds": {
                        "ButtonPlayerNum": 1,
                        "SmallBlindPlayerNum": 2,
                        "SmallBlindAmt": 50,
                        "BigBlindPlayerNum": 1,
                        "BigBlindAmt": 100,
                        "AnteType": "BB_ANTE_BB1ST",
                        "BlindLevel": 1,
                    },
                }
            ],
            "ID": 638961999170907267,
            "Payouts": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "SoftwareVersion": "PokerGFX 3.2",
            "Type": "FEATURE_TABLE",
        }

    def test_convert_card_lowercase_face_cards(self, parser: PokerGFXFileParser):
        """Test card conversion for lowercase face cards."""
        assert parser._convert_card("as") == "As"
        assert parser._convert_card("kd") == "Kd"
        assert parser._convert_card("qh") == "Qh"
        assert parser._convert_card("jc") == "Jc"

    def test_convert_card_number_cards(self, parser: PokerGFXFileParser):
        """Test card conversion for number cards."""
        assert parser._convert_card("7s") == "7s"
        assert parser._convert_card("2d") == "2d"
        assert parser._convert_card("9h") == "9h"

    def test_convert_card_ten(self, parser: PokerGFXFileParser):
        """Test card conversion for ten (10 -> T)."""
        assert parser._convert_card("10h") == "Th"
        assert parser._convert_card("10s") == "Ts"

    def test_parse_duration_minutes_seconds(self, parser: PokerGFXFileParser):
        """Test ISO 8601 duration parsing with minutes and seconds."""
        assert parser._parse_duration("PT2M56S") == 176
        assert parser._parse_duration("PT1M30S") == 90
        assert parser._parse_duration("PT0M45S") == 45

    def test_parse_duration_with_fractional_seconds(self, parser: PokerGFXFileParser):
        """Test duration parsing with fractional seconds."""
        assert parser._parse_duration("PT2M56.2628165S") == 176

    def test_parse_duration_hours(self, parser: PokerGFXFileParser):
        """Test duration parsing with hours."""
        assert parser._parse_duration("PT1H30M0S") == 5400
        assert parser._parse_duration("PT1H0M0S") == 3600

    def test_parse_duration_seconds_only(self, parser: PokerGFXFileParser):
        """Test duration parsing with seconds only."""
        assert parser._parse_duration("PT45S") == 45
        assert parser._parse_duration("PT120S") == 120

    def test_parse_duration_empty(self, parser: PokerGFXFileParser):
        """Test duration parsing with empty string."""
        assert parser._parse_duration("") == 0
        assert parser._parse_duration("PT0S") == 0

    def test_parse_datetime(self, parser: PokerGFXFileParser):
        """Test ISO 8601 datetime parsing."""
        dt = parser._parse_datetime("2025-10-16T08:25:17.0907267Z")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 10
        assert dt.day == 16

    def test_parse_datetime_empty(self, parser: PokerGFXFileParser):
        """Test datetime parsing with empty string."""
        assert parser._parse_datetime("") is None

    def test_extract_community_cards(
        self, parser: PokerGFXFileParser, sample_session_data: dict
    ):
        """Test extraction of community cards from events."""
        events = sample_session_data["Hands"][0]["Events"]
        cards = parser._extract_community_cards(events)

        assert len(cards) == 5
        assert str(cards[0]) == "Ah"  # From first BOARD CARD event
        assert str(cards[1]) == "Kc"
        assert str(cards[2]) == "7s"
        assert str(cards[3]) == "2d"  # Turn
        assert str(cards[4]) == "3h"  # River

    def test_extract_final_pot(
        self, parser: PokerGFXFileParser, sample_session_data: dict
    ):
        """Test final pot extraction from events."""
        events = sample_session_data["Hands"][0]["Events"]
        pot = parser._extract_final_pot(events)
        assert pot == 1700

    def test_find_winner(self, parser: PokerGFXFileParser, sample_session_data: dict):
        """Test winner detection from stack changes."""
        hand_data = sample_session_data["Hands"][0]
        winner = parser._find_winner(hand_data)
        assert winner == "Player A"  # Won 5000 chips

    def test_get_hand_rank(self, parser: PokerGFXFileParser):
        """Test phevaluator rank to HandRank conversion."""
        assert parser._get_hand_rank(1) == HandRank.ROYAL_FLUSH
        assert parser._get_hand_rank(5) == HandRank.STRAIGHT_FLUSH
        assert parser._get_hand_rank(100) == HandRank.FOUR_OF_A_KIND
        assert parser._get_hand_rank(200) == HandRank.FULL_HOUSE
        assert parser._get_hand_rank(500) == HandRank.FLUSH
        assert parser._get_hand_rank(1605) == HandRank.STRAIGHT
        assert parser._get_hand_rank(2000) == HandRank.THREE_OF_A_KIND
        assert parser._get_hand_rank(3000) == HandRank.TWO_PAIR
        assert parser._get_hand_rank(5000) == HandRank.ONE_PAIR
        assert parser._get_hand_rank(7000) == HandRank.HIGH_CARD

    def test_parse_session_data(
        self, parser: PokerGFXFileParser, sample_session_data: dict
    ):
        """Test full session parsing."""
        results = parser.parse_session_data(sample_session_data)

        # Should have 2 results (one for each player with hole cards)
        assert len(results) == 2

        # Check first result (Player A with As Kd)
        player_a_result = next(
            r for r in results if "Player A" in str(r.players_showdown)
        )
        assert player_a_result.hand_number == 1
        assert player_a_result.confidence == 1.0
        assert player_a_result.pot_size == 1700
        assert player_a_result.winner == "Player A"

        # Player A should have two pair (Aces and Kings) or better
        # As + Kd + Ah + Kc + 7s + 2d + 3h
        assert player_a_result.hand_rank in [
            HandRank.TWO_PAIR,
            HandRank.FULL_HOUSE,  # If evaluated differently
        ]

    def test_parse_session_metadata(
        self, parser: PokerGFXFileParser, sample_session_data: dict
    ):
        """Test session metadata parsing."""
        session = parser.parse_session_metadata(sample_session_data)

        assert session.session_id == 638961999170907267
        assert session.software_version == "PokerGFX 3.2"
        assert session.table_type == "FEATURE_TABLE"
        assert session.event_title == "Feature Table Session"
        assert len(session.hands) == 1


class TestJSONFileWatcher:
    """Tests for JSONFileWatcher class."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock PokerGFX settings."""
        settings = MagicMock()
        settings.mode = "json"
        settings.json_watch_path = ""
        settings.polling_interval = 1.0
        settings.processed_db_path = ""
        settings.file_pattern = "*.json"
        settings.file_settle_delay = 0.1
        return settings

    @pytest.fixture
    def temp_watch_dir(self):
        """Create temporary watch directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_json_file(self, temp_watch_dir: Path) -> Path:
        """Create sample JSON file in temp directory."""
        data = {
            "CreatedDateTimeUTC": "2025-10-16T08:25:17Z",
            "Hands": [
                {
                    "HandNum": 1,
                    "Duration": "PT1M30S",
                    "StartDateTimeUTC": "2025-10-16T08:28:43Z",
                    "Players": [
                        {
                            "PlayerNum": 1,
                            "Name": "Test Player",
                            "HoleCards": ["as", "ks"],
                            "StartStackAmt": 10000,
                            "EndStackAmt": 12000,
                        }
                    ],
                    "Events": [
                        {
                            "EventType": "BOARD CARD",
                            "BoardCards": ["ah", "kh", "7s", "2d", "3c"],
                        },
                        {"EventType": "BET", "Pot": 5000},
                    ],
                }
            ],
            "ID": 12345,
            "Type": "FEATURE_TABLE",
            "SoftwareVersion": "PokerGFX 3.2",
        }

        filepath = temp_watch_dir / "session_12345.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)

        return filepath

    def test_watcher_initialization(self, mock_settings, temp_watch_dir: Path):
        """Test watcher initialization."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        watcher = JSONFileWatcher(mock_settings)

        assert watcher.settings == mock_settings
        assert watcher._running is False
        assert len(watcher._processed_files) == 0

    def test_is_processed(self, mock_settings, temp_watch_dir: Path):
        """Test processed file tracking."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        watcher = JSONFileWatcher(mock_settings)

        assert watcher._is_processed("test.json") is False

        watcher._save_processed_file("test.json")
        assert watcher._is_processed("test.json") is True

    def test_processed_files_persistence(self, mock_settings, temp_watch_dir: Path):
        """Test that processed files are persisted to disk."""
        db_path = temp_watch_dir / "processed.json"
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(db_path)

        # First watcher saves a file
        watcher1 = JSONFileWatcher(mock_settings)
        watcher1._save_processed_file("test1.json")
        watcher1._save_processed_file("test2.json")

        # Second watcher should load the saved files
        watcher2 = JSONFileWatcher(mock_settings)
        assert watcher2._is_processed("test1.json") is True
        assert watcher2._is_processed("test2.json") is True
        assert watcher2._is_processed("test3.json") is False

    async def test_check_nas_connection_valid(
        self, mock_settings, temp_watch_dir: Path
    ):
        """Test NAS connection check with valid path."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        assert await watcher._check_nas_connection() is True

    async def test_check_nas_connection_invalid(self, mock_settings):
        """Test NAS connection check with invalid path."""
        mock_settings.json_watch_path = "/nonexistent/path/that/does/not/exist"
        mock_settings.processed_db_path = "/tmp/processed.json"

        watcher = JSONFileWatcher(mock_settings)
        assert await watcher._check_nas_connection() is False

    async def test_process_file(
        self, mock_settings, temp_watch_dir: Path, sample_json_file: Path
    ):
        """Test processing a JSON file."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        results = await watcher._process_file(str(sample_json_file))

        assert len(results) == 1
        assert results[0].hand_number == 1
        assert watcher._is_processed(sample_json_file.name) is True

    async def test_process_file_skip_duplicate(
        self, mock_settings, temp_watch_dir: Path, sample_json_file: Path
    ):
        """Test that duplicate files are skipped."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        watcher = JSONFileWatcher(mock_settings)

        # Process once
        results1 = await watcher._process_file(str(sample_json_file))
        assert len(results1) == 1

        # Process again - should skip
        results2 = await watcher._process_file(str(sample_json_file))
        assert len(results2) == 0

    async def test_process_corrupted_file(self, mock_settings, temp_watch_dir: Path):
        """Test handling of corrupted JSON file."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        # Create corrupted JSON file
        corrupted_file = temp_watch_dir / "corrupted.json"
        corrupted_file.write_text("{ invalid json }")

        watcher = JSONFileWatcher(mock_settings)
        results = await watcher._process_file(str(corrupted_file))

        assert len(results) == 0
        # File should be moved to errors folder
        error_dir = temp_watch_dir / "errors"
        assert error_dir.exists()

    def test_get_stats(self, mock_settings, temp_watch_dir: Path):
        """Test statistics retrieval."""
        mock_settings.json_watch_path = str(temp_watch_dir)
        mock_settings.processed_db_path = str(temp_watch_dir / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        watcher._save_processed_file("test1.json")
        watcher._save_processed_file("test2.json")

        stats = watcher.get_stats()

        assert stats["processed_files_count"] == 2
        assert stats["watch_path"] == str(temp_watch_dir)
        assert stats["polling_interval"] == 1.0
        assert stats["is_running"] is False


class TestIntegration:
    """Integration tests for file watcher and parser."""

    @pytest.fixture
    def temp_watch_dir(self):
        """Create temporary watch directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mock_settings(self, temp_watch_dir: Path):
        """Create mock settings with temp directory."""
        settings = MagicMock()
        settings.mode = "json"
        settings.json_watch_path = str(temp_watch_dir)
        settings.polling_interval = 0.5
        settings.processed_db_path = str(temp_watch_dir / "processed.json")
        settings.file_pattern = "*.json"
        settings.file_settle_delay = 0.1
        return settings

    async def test_process_existing_files(
        self, mock_settings, temp_watch_dir: Path
    ):
        """Test processing of existing files on startup."""
        # Create multiple JSON files
        for i in range(3):
            data = {
                "CreatedDateTimeUTC": f"2025-10-16T0{i}:00:00Z",
                "Hands": [
                    {
                        "HandNum": i + 1,
                        "Duration": "PT1M0S",
                        "StartDateTimeUTC": f"2025-10-16T0{i}:00:00Z",
                        "Players": [
                            {
                                "PlayerNum": 1,
                                "Name": f"Player {i}",
                                "HoleCards": ["as", "ks"],
                                "StartStackAmt": 10000,
                                "EndStackAmt": 11000,
                            }
                        ],
                        "Events": [
                            {
                                "EventType": "BOARD CARD",
                                "BoardCards": ["ah", "kh", "7s", "2d", "3c"],
                            },
                            {"EventType": "BET", "Pot": 1000},
                        ],
                    }
                ],
                "ID": 12345 + i,
                "Type": "FEATURE_TABLE",
                "SoftwareVersion": "PokerGFX 3.2",
            }
            filepath = temp_watch_dir / f"session_{12345 + i}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f)

        watcher = JSONFileWatcher(mock_settings)

        # Collect results from existing files
        results = []
        async for result in watcher._process_existing_files():
            results.append(result)

        assert len(results) == 3
        hand_numbers = {r.hand_number for r in results}
        assert hand_numbers == {1, 2, 3}
