"""Tests for GFX JSON Simulator."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.simulator.gfx_json_simulator import (
    GFXJsonSimulator,
    LogEntry,
    SimulationProgress,
    Status,
)
from src.simulator.hand_splitter import HandSplitter


# Sample test data matching GFX JSON structure
SAMPLE_JSON = {
    "CreatedDateTimeUTC": "2025-10-20T10:45:56.1171011Z",
    "EventTitle": "Test Tournament",
    "Hands": [
        {
            "HandNum": 1,
            "Duration": "PT1M10S",
            "StartDateTimeUTC": "2025-10-20T10:56:40Z",
            "GameVariant": "HOLDEM",
            "Players": [{"Name": "Player1", "PlayerNum": 1}],
            "Events": [{"EventType": "FOLD", "PlayerNum": 1}],
        },
        {
            "HandNum": 3,  # Out of order to test sorting
            "Duration": "PT2M30S",
            "StartDateTimeUTC": "2025-10-20T11:00:00Z",
            "GameVariant": "HOLDEM",
            "Players": [{"Name": "Player1", "PlayerNum": 1}],
            "Events": [{"EventType": "BET", "PlayerNum": 1}],
        },
        {
            "HandNum": 2,
            "Duration": "PT1M29S",
            "StartDateTimeUTC": "2025-10-20T10:58:21Z",
            "GameVariant": "HOLDEM",
            "Players": [{"Name": "Player1", "PlayerNum": 1}],
            "Events": [{"EventType": "CALL", "PlayerNum": 1}],
        },
    ],
}


class TestHandSplitter:
    """Tests for HandSplitter class."""

    def test_split_hands_sorts_by_hand_num(self) -> None:
        """split_hands should sort hands by HandNum."""
        hands = HandSplitter.split_hands(SAMPLE_JSON)

        assert len(hands) == 3
        assert hands[0]["HandNum"] == 1
        assert hands[1]["HandNum"] == 2
        assert hands[2]["HandNum"] == 3

    def test_split_hands_empty(self) -> None:
        """split_hands should handle empty hands array."""
        data = {"CreatedDateTimeUTC": "", "EventTitle": "", "Hands": []}
        hands = HandSplitter.split_hands(data)

        assert hands == []

    def test_split_hands_missing_hands_key(self) -> None:
        """split_hands should handle missing Hands key."""
        data = {"CreatedDateTimeUTC": "", "EventTitle": ""}
        hands = HandSplitter.split_hands(data)

        assert hands == []

    def test_build_cumulative_single_hand(self) -> None:
        """build_cumulative should create JSON with single hand."""
        hands = HandSplitter.split_hands(SAMPLE_JSON)
        metadata = HandSplitter.extract_metadata(SAMPLE_JSON)

        result = HandSplitter.build_cumulative(hands, 1, metadata)

        assert result["CreatedDateTimeUTC"] == SAMPLE_JSON["CreatedDateTimeUTC"]
        assert result["EventTitle"] == SAMPLE_JSON["EventTitle"]
        assert len(result["Hands"]) == 1
        assert result["Hands"][0]["HandNum"] == 1

    def test_build_cumulative_multiple_hands(self) -> None:
        """build_cumulative should create JSON with multiple hands."""
        hands = HandSplitter.split_hands(SAMPLE_JSON)
        metadata = HandSplitter.extract_metadata(SAMPLE_JSON)

        result = HandSplitter.build_cumulative(hands, 2, metadata)

        assert len(result["Hands"]) == 2
        assert result["Hands"][0]["HandNum"] == 1
        assert result["Hands"][1]["HandNum"] == 2

    def test_build_cumulative_all_hands(self) -> None:
        """build_cumulative should create JSON with all hands."""
        hands = HandSplitter.split_hands(SAMPLE_JSON)
        metadata = HandSplitter.extract_metadata(SAMPLE_JSON)

        result = HandSplitter.build_cumulative(hands, 3, metadata)

        assert len(result["Hands"]) == 3

    def test_get_hand_count(self) -> None:
        """get_hand_count should return correct count."""
        count = HandSplitter.get_hand_count(SAMPLE_JSON)
        assert count == 3

    def test_get_hand_count_empty(self) -> None:
        """get_hand_count should return 0 for empty data."""
        count = HandSplitter.get_hand_count({})
        assert count == 0

    def test_extract_metadata(self) -> None:
        """extract_metadata should extract non-Hands fields."""
        metadata = HandSplitter.extract_metadata(SAMPLE_JSON)

        assert metadata["CreatedDateTimeUTC"] == SAMPLE_JSON["CreatedDateTimeUTC"]
        assert metadata["EventTitle"] == SAMPLE_JSON["EventTitle"]
        assert "Hands" not in metadata


class TestLogEntry:
    """Tests for LogEntry class."""

    def test_log_entry_str(self) -> None:
        """LogEntry should format as string correctly."""
        from datetime import datetime

        entry = LogEntry(
            timestamp=datetime(2025, 10, 20, 12, 30, 45),
            level="INFO",
            message="Test message",
            table_name="table-GG",
        )

        result = str(entry)
        assert "[12:30:45]" in result
        assert "OK" in result
        assert "Test message" in result
        assert "(table-GG)" in result

    def test_log_entry_icon(self) -> None:
        """LogEntry should return correct icon for level."""
        from datetime import datetime

        ts = datetime.now()

        assert LogEntry(ts, "INFO", "").icon == "OK"
        assert LogEntry(ts, "WARNING", "").icon == "WARN"
        assert LogEntry(ts, "ERROR", "").icon == "ERR"
        assert LogEntry(ts, "SUCCESS", "").icon == "OK"


class TestSimulationProgress:
    """Tests for SimulationProgress class."""

    def test_progress_calculation(self) -> None:
        """progress should calculate percentage correctly."""
        p = SimulationProgress(current_hand=5, total_hands=10)
        assert p.progress == 0.5

    def test_progress_zero_total(self) -> None:
        """progress should return 0 when total is 0."""
        p = SimulationProgress(current_hand=0, total_hands=0)
        assert p.progress == 0.0

    def test_elapsed_seconds(self) -> None:
        """elapsed_seconds should calculate time since start."""
        from datetime import datetime, timedelta

        start = datetime.now() - timedelta(seconds=30)
        p = SimulationProgress(start_time=start)

        assert 29 <= p.elapsed_seconds <= 31

    def test_elapsed_seconds_no_start(self) -> None:
        """elapsed_seconds should return 0 when not started."""
        p = SimulationProgress()
        assert p.elapsed_seconds == 0.0


class TestGFXJsonSimulator:
    """Tests for GFXJsonSimulator class."""

    @pytest.fixture
    def temp_dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create temporary source and target directories."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        return source, target

    @pytest.fixture
    def sample_json_file(self, temp_dirs: tuple[Path, Path]) -> Path:
        """Create sample JSON file in source directory."""
        source, _ = temp_dirs
        table_dir = source / "table-test"
        table_dir.mkdir()

        json_path = table_dir / "test_game.json"
        json_path.write_text(json.dumps(SAMPLE_JSON), encoding="utf-8")

        return json_path

    def test_simulator_init(self, temp_dirs: tuple[Path, Path]) -> None:
        """Simulator should initialize with correct defaults."""
        source, target = temp_dirs

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=5,
        )

        assert sim.status == Status.IDLE
        assert sim.interval == 5
        assert sim.progress.current_hand == 0

    def test_simulator_log(self, temp_dirs: tuple[Path, Path]) -> None:
        """Simulator should add log entries."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)

        sim._log("Test message", "INFO", "table-test")

        assert len(sim.logs) == 1
        assert sim.logs[0].message == "Test message"
        assert sim.logs[0].table_name == "table-test"

    def test_simulator_log_limit(self, temp_dirs: tuple[Path, Path]) -> None:
        """Simulator should limit logs to 100 entries."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)

        for i in range(150):
            sim._log(f"Message {i}")

        assert len(sim.logs) == 100
        assert sim.logs[0].message == "Message 50"

    def test_simulator_stop(self, temp_dirs: tuple[Path, Path]) -> None:
        """Simulator should set stop flag."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)

        sim.stop()

        assert sim._stop_requested is True
        assert sim.status == Status.STOPPED

    def test_discover_json_files(
        self, temp_dirs: tuple[Path, Path], sample_json_file: Path
    ) -> None:
        """Simulator should discover JSON files in source."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)

        files = sim._discover_json_files()

        assert len(files) == 1
        assert files[0] == sample_json_file

    async def test_simulate_file(
        self, temp_dirs: tuple[Path, Path], sample_json_file: Path
    ) -> None:
        """Simulator should create cumulative JSON files."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,  # No delay for test
        )

        success = await sim.simulate_file(sample_json_file)

        assert success is True

        # Check output file exists
        output_path = target / "table-test" / "test_game.json"
        assert output_path.exists()

        # Check final output has all hands
        data = json.loads(output_path.read_text())
        assert len(data["Hands"]) == 3

    async def test_simulate_file_invalid_json(
        self, temp_dirs: tuple[Path, Path]
    ) -> None:
        """Simulator should handle invalid JSON gracefully."""
        source, target = temp_dirs
        invalid_file = source / "invalid.json"
        invalid_file.write_text("not valid json", encoding="utf-8")

        sim = GFXJsonSimulator(source_path=source, target_path=target)

        success = await sim.simulate_file(invalid_file)

        assert success is False

    async def test_run_empty_source(self, temp_dirs: tuple[Path, Path]) -> None:
        """Simulator should handle empty source directory."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)

        await sim.run()

        assert sim.status == Status.COMPLETED

    async def test_run_full_simulation(
        self, temp_dirs: tuple[Path, Path], sample_json_file: Path
    ) -> None:
        """Simulator should run full simulation successfully."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        assert sim.status == Status.COMPLETED
        assert sim.progress.current_hand == 3
        assert sim.progress.total_hands == 3

        # Check output
        output_path = target / "table-test" / "test_game.json"
        assert output_path.exists()

    def test_write_with_retry_success(self, temp_dirs: tuple[Path, Path]) -> None:
        """_write_with_retry should succeed on first attempt."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)

        output_file = target / "test.json"
        success = sim._write_with_retry(output_file, '{"test": true}')

        assert success is True
        assert output_file.exists()
        assert json.loads(output_file.read_text()) == {"test": True}

    def test_pause_changes_status(self, temp_dirs: tuple[Path, Path]) -> None:
        """pause() should change status to PAUSED."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)
        sim.status = Status.RUNNING

        sim.pause()

        assert sim.status == Status.PAUSED
        assert not sim._pause_event.is_set()

    def test_resume_changes_status(self, temp_dirs: tuple[Path, Path]) -> None:
        """resume() should change status to RUNNING."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)
        sim.status = Status.PAUSED
        sim._pause_event.clear()

        sim.resume()

        assert sim.status == Status.RUNNING
        assert sim._pause_event.is_set()

    def test_pause_only_when_running(self, temp_dirs: tuple[Path, Path]) -> None:
        """pause() should only work when status is RUNNING."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)
        sim.status = Status.IDLE

        sim.pause()

        # Should not change status
        assert sim.status == Status.IDLE

    def test_resume_only_when_paused(self, temp_dirs: tuple[Path, Path]) -> None:
        """resume() should only work when status is PAUSED."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(source_path=source, target_path=target)
        sim.status = Status.RUNNING

        sim.resume()

        # Should not change status
        assert sim.status == Status.RUNNING

    def test_checkpoint_update(
        self, temp_dirs: tuple[Path, Path], sample_json_file: Path
    ) -> None:
        """Checkpoint should be updated during simulation."""
        source, target = temp_dirs
        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        import asyncio
        asyncio.run(sim.run())

        checkpoint = sim.get_checkpoint()
        assert checkpoint.file_index == 0
        assert checkpoint.hand_index == 3  # Last hand in sample file
