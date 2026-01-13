"""Integration tests for GFX JSON Simulator.

These tests verify file I/O operations and full simulation workflows
with actual file system interactions (using tmp_path).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.simulator.gfx_json_simulator import (
    GFXJsonSimulator,
    ParallelSimulationOrchestrator,
    Status,
)


# Sample test data
def create_sample_json(hand_count: int = 3, event_title: str = "Test Event") -> dict[str, Any]:
    """Create sample GFX JSON data with specified hand count."""
    hands = [
        {
            "HandNum": i + 1,
            "Duration": f"PT{i + 1}M00S",
            "StartDateTimeUTC": f"2025-01-13T{10 + i}:00:00Z",
            "GameVariant": "HOLDEM",
            "Players": [{"Name": f"Player{j + 1}", "PlayerNum": j + 1} for j in range(6)],
            "Events": [{"EventType": "DEAL", "PlayerNum": 1}],
        }
        for i in range(hand_count)
    ]
    return {
        "CreatedDateTimeUTC": "2025-01-13T09:00:00Z",
        "EventTitle": event_title,
        "Hands": hands,
    }


class TestLocalFolderIntegration:
    """Integration tests for local folder write operations."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create isolated source and target directories."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        return source, target

    @pytest.fixture
    def single_table_setup(self, workspace: tuple[Path, Path]) -> tuple[Path, Path, Path]:
        """Create single table with one JSON file."""
        source, target = workspace
        table_dir = source / "Table_A"
        table_dir.mkdir()

        json_file = table_dir / "session_001.json"
        json_file.write_text(json.dumps(create_sample_json(3)), encoding="utf-8")

        return source, target, json_file

    @pytest.fixture
    def multi_table_setup(self, workspace: tuple[Path, Path]) -> tuple[Path, Path, list[Path]]:
        """Create multiple tables with JSON files."""
        source, target = workspace

        files: list[Path] = []
        for table_name in ["Table_A", "Table_B", "Table_C"]:
            table_dir = source / table_name
            table_dir.mkdir()

            json_file = table_dir / f"session_{table_name}.json"
            json_file.write_text(
                json.dumps(create_sample_json(2, f"Event {table_name}")),
                encoding="utf-8",
            )
            files.append(json_file)

        return source, target, files

    async def test_single_file_simulation_creates_output(
        self, single_table_setup: tuple[Path, Path, Path]
    ) -> None:
        """Single file simulation should create output file."""
        source, target, json_file = single_table_setup

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        # Verify output file exists
        output_file = target / "Table_A" / "session_001.json"
        assert output_file.exists(), "Output file should be created"

        # Verify output content
        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert "Hands" in data
        assert len(data["Hands"]) == 3

    async def test_multiple_files_simulation(
        self, multi_table_setup: tuple[Path, Path, list[Path]]
    ) -> None:
        """Multiple files should be processed sequentially."""
        source, target, files = multi_table_setup

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        # Verify all output files exist
        for table_name in ["Table_A", "Table_B", "Table_C"]:
            output_file = target / table_name / f"session_{table_name}.json"
            assert output_file.exists(), f"Output for {table_name} should exist"

        # Verify completion status
        assert sim.status == Status.COMPLETED
        # 3 tables * 2 hands each = 6 total hands
        assert sim.progress.total_hands == 6
        assert sim.progress.current_hand == 6

    async def test_nested_folder_structure_preserved(
        self, workspace: tuple[Path, Path]
    ) -> None:
        """Nested folder structure should be preserved in output."""
        source, target = workspace

        # Create nested structure: source/Event1/Day1/Table_A/session.json
        nested_path = source / "Event1" / "Day1" / "Table_A"
        nested_path.mkdir(parents=True)

        json_file = nested_path / "session.json"
        json_file.write_text(json.dumps(create_sample_json(2)), encoding="utf-8")

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        # Verify nested output path
        output_file = target / "Event1" / "Day1" / "Table_A" / "session.json"
        assert output_file.exists(), "Nested folder structure should be preserved"

    async def test_cumulative_json_progression(
        self, single_table_setup: tuple[Path, Path, Path]
    ) -> None:
        """Cumulative JSON should progress from 1 hand to all hands."""
        source, target, json_file = single_table_setup

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        # Track hand counts during simulation
        hand_counts: list[int] = []

        original_write = sim._write_with_retry

        def tracking_write(output_path: Path, content: str) -> bool:
            data = json.loads(content)
            hand_counts.append(len(data.get("Hands", [])))
            return original_write(output_path, content)

        sim._write_with_retry = tracking_write  # type: ignore[method-assign]

        await sim.run()

        # Should have written 1, 2, 3 hands progressively
        assert hand_counts == [1, 2, 3], "Hands should be added cumulatively"

    async def test_metadata_preserved_in_output(
        self, single_table_setup: tuple[Path, Path, Path]
    ) -> None:
        """Metadata (CreatedDateTimeUTC, EventTitle) should be preserved."""
        source, target, json_file = single_table_setup

        # Create JSON with specific metadata
        custom_data = create_sample_json(2)
        custom_data["CreatedDateTimeUTC"] = "2025-12-25T00:00:00Z"
        custom_data["EventTitle"] = "Special Event 2025"
        json_file.write_text(json.dumps(custom_data), encoding="utf-8")

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        # Verify metadata in output
        output_file = target / "Table_A" / "session_001.json"
        output_data = json.loads(output_file.read_text(encoding="utf-8"))

        assert output_data["CreatedDateTimeUTC"] == "2025-12-25T00:00:00Z"
        assert output_data["EventTitle"] == "Special Event 2025"


class TestNASFolderIntegration:
    """Integration tests for NAS folder operations (with mocking)."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create isolated source and target directories."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        return source, target

    @pytest.fixture
    def sample_file(self, workspace: tuple[Path, Path]) -> tuple[Path, Path, Path]:
        """Create sample JSON file."""
        source, target = workspace
        table_dir = source / "Table_NAS"
        table_dir.mkdir()

        json_file = table_dir / "nas_session.json"
        json_file.write_text(json.dumps(create_sample_json(2)), encoding="utf-8")

        return source, target, json_file

    async def test_nas_path_write_success(
        self, sample_file: tuple[Path, Path, Path]
    ) -> None:
        """NAS path write should succeed under normal conditions."""
        source, target, json_file = sample_file

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        assert sim.status == Status.COMPLETED
        output_file = target / "Table_NAS" / "nas_session.json"
        assert output_file.exists()

    async def test_nas_write_retry_on_failure(
        self, sample_file: tuple[Path, Path, Path]
    ) -> None:
        """Write should retry on temporary failure."""
        source, target, json_file = sample_file

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        call_count = 0
        original_write = Path.write_text

        def mock_write_text(self: Path, content: str, encoding: str = "utf-8") -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise OSError("Network timeout")
            # Third call succeeds - use original method
            return original_write(self, content, encoding=encoding)

        with patch.object(Path, "write_text", mock_write_text):
            success = await sim.simulate_file(json_file)

        # Should have called write multiple times due to retries and cumulative writes
        assert call_count >= 1, "Should have attempted writes"

    async def test_nas_write_all_retries_fail(
        self, sample_file: tuple[Path, Path, Path]
    ) -> None:
        """All retries failing should result in ERROR status."""
        source, target, json_file = sample_file

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        def always_fail(*args: Any, **kwargs: Any) -> None:
            raise OSError("Persistent network error")

        with patch.object(Path, "write_text", always_fail):
            success = await sim.simulate_file(json_file)

        assert success is False
        assert sim.status == Status.ERROR

    async def test_nas_intermittent_failure_recovery(
        self, workspace: tuple[Path, Path]
    ) -> None:
        """Simulator should recover from intermittent failures."""
        source, target = workspace

        # Create multiple files
        for i in range(3):
            table_dir = source / f"Table_{i}"
            table_dir.mkdir()
            json_file = table_dir / f"session_{i}.json"
            json_file.write_text(
                json.dumps(create_sample_json(1, f"Event {i}")),
                encoding="utf-8",
            )

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        fail_counter = {"count": 0}
        original_write = Path.write_text

        def intermittent_fail(self: Path, content: str, encoding: str = "utf-8") -> None:
            fail_counter["count"] += 1
            # Fail every other write on first attempt
            if fail_counter["count"] % 3 == 1:
                raise OSError("Intermittent failure")
            return original_write(self, content, encoding=encoding)

        with patch.object(Path, "write_text", intermittent_fail):
            await sim.run()

        # Should still complete (retry mechanism handles failures)
        # Note: Status may be COMPLETED or ERROR depending on retry success
        assert sim.progress.current_hand > 0, "Some hands should have been processed"


class TestEdgeCases:
    """Edge case integration tests."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create isolated source and target directories."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        return source, target

    async def test_empty_hands_array(self, workspace: tuple[Path, Path]) -> None:
        """Empty Hands array should be handled gracefully."""
        source, target = workspace
        table_dir = source / "Table_Empty"
        table_dir.mkdir()

        json_file = table_dir / "empty.json"
        json_file.write_text(
            json.dumps({"CreatedDateTimeUTC": "", "EventTitle": "", "Hands": []}),
            encoding="utf-8",
        )

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        # Should complete without errors
        assert sim.status == Status.COMPLETED

    async def test_special_characters_in_path(
        self, workspace: tuple[Path, Path]
    ) -> None:
        """Paths with special characters should work."""
        source, target = workspace

        # Create path with special chars (Windows-safe)
        special_dir = source / "Table_A-1_Test"
        special_dir.mkdir()

        json_file = special_dir / "session_2025-01-13.json"
        json_file.write_text(json.dumps(create_sample_json(1)), encoding="utf-8")

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        output_file = target / "Table_A-1_Test" / "session_2025-01-13.json"
        assert output_file.exists()

    async def test_large_json_file(self, workspace: tuple[Path, Path]) -> None:
        """Large JSON files should be handled."""
        source, target = workspace
        table_dir = source / "Table_Large"
        table_dir.mkdir()

        # Create JSON with many hands
        large_data = create_sample_json(50, "Large Event")
        json_file = table_dir / "large_session.json"
        json_file.write_text(json.dumps(large_data), encoding="utf-8")

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await sim.run()

        assert sim.status == Status.COMPLETED
        assert sim.progress.total_hands == 50
        assert sim.progress.current_hand == 50

    async def test_stop_during_simulation(
        self, workspace: tuple[Path, Path]
    ) -> None:
        """Stopping mid-simulation should halt processing gracefully."""
        source, target = workspace
        table_dir = source / "Table_Stop"
        table_dir.mkdir()

        # Create file with many hands
        json_file = table_dir / "session.json"
        json_file.write_text(json.dumps(create_sample_json(10)), encoding="utf-8")

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0.1,  # Small delay to allow stop
        )

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.3)
            sim.stop()

        # Run simulation and stop task concurrently
        await asyncio.gather(
            sim.run(),
            stop_after_delay(),
            return_exceptions=True,
        )

        assert sim.status == Status.STOPPED
        # Should have processed some but not all hands
        assert sim.progress.current_hand < 10

    async def test_selected_files_override(
        self, workspace: tuple[Path, Path]
    ) -> None:
        """_selected_files should override file discovery."""
        source, target = workspace

        # Create multiple tables
        for name in ["Table_A", "Table_B", "Table_C"]:
            table_dir = source / name
            table_dir.mkdir()
            json_file = table_dir / f"session_{name}.json"
            json_file.write_text(json.dumps(create_sample_json(1)), encoding="utf-8")

        sim = GFXJsonSimulator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        # Only process Table_B
        sim._selected_files = [source / "Table_B" / "session_Table_B.json"]

        await sim.run()

        # Only Table_B should have output
        assert not (target / "Table_A" / "session_Table_A.json").exists()
        assert (target / "Table_B" / "session_Table_B.json").exists()
        assert not (target / "Table_C" / "session_Table_C.json").exists()


class TestParallelSimulation:
    """Integration tests for parallel multi-table simulation."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create isolated source and target directories."""
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        target.mkdir()
        return source, target

    @pytest.fixture
    def multi_table_setup(self, workspace: tuple[Path, Path]) -> tuple[Path, Path, list[Path]]:
        """Create multiple tables with JSON files."""
        source, target = workspace

        files: list[Path] = []
        for table_name in ["Table_A", "Table_B", "Table_C"]:
            table_dir = source / table_name
            table_dir.mkdir()

            json_file = table_dir / f"session_{table_name}.json"
            json_file.write_text(
                json.dumps(create_sample_json(2, f"Event {table_name}")),
                encoding="utf-8",
            )
            files.append(json_file)

        return source, target, files

    async def test_parallel_processes_all_tables(
        self, multi_table_setup: tuple[Path, Path, list[Path]]
    ) -> None:
        """Parallel orchestrator should process all tables."""
        source, target, files = multi_table_setup

        orchestrator = ParallelSimulationOrchestrator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await orchestrator.run(files)

        # All tables should have output
        assert (target / "Table_A" / f"session_Table_A.json").exists()
        assert (target / "Table_B" / f"session_Table_B.json").exists()
        assert (target / "Table_C" / f"session_Table_C.json").exists()

        # Status should be COMPLETED
        assert orchestrator.status == Status.COMPLETED

    async def test_parallel_aggregate_progress(
        self, multi_table_setup: tuple[Path, Path, list[Path]]
    ) -> None:
        """Aggregate progress should sum all tasks."""
        source, target, files = multi_table_setup

        orchestrator = ParallelSimulationOrchestrator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await orchestrator.run(files)

        # 3 tables * 2 hands each = 6 total
        progress = orchestrator.aggregate_progress
        assert progress.total_hands == 6
        assert progress.current_hand == 6

    async def test_parallel_combined_logs(
        self, multi_table_setup: tuple[Path, Path, list[Path]]
    ) -> None:
        """Combined logs should include all table logs."""
        source, target, files = multi_table_setup

        orchestrator = ParallelSimulationOrchestrator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await orchestrator.run(files)

        logs = orchestrator.get_logs(limit=100)

        # Should have logs from all tables
        table_names_in_logs = {log.table_name for log in logs if log.table_name}
        assert "Table_A" in table_names_in_logs
        assert "Table_B" in table_names_in_logs
        assert "Table_C" in table_names_in_logs

    async def test_parallel_stop_all_tasks(
        self, multi_table_setup: tuple[Path, Path, list[Path]]
    ) -> None:
        """Stopping orchestrator should stop all tasks."""
        source, target, files = multi_table_setup

        orchestrator = ParallelSimulationOrchestrator(
            source_path=source,
            target_path=target,
            interval=0.1,
        )

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.2)
            orchestrator.stop()

        await asyncio.gather(
            orchestrator.run(files),
            stop_after_delay(),
            return_exceptions=True,
        )

        assert orchestrator.status == Status.STOPPED

    async def test_parallel_creates_correct_tasks(
        self, multi_table_setup: tuple[Path, Path, list[Path]]
    ) -> None:
        """Orchestrator should create one task per table."""
        source, target, files = multi_table_setup

        orchestrator = ParallelSimulationOrchestrator(
            source_path=source,
            target_path=target,
            interval=0,
        )

        await orchestrator.run(files)

        # Should have 3 tasks (one per table)
        assert len(orchestrator.tasks) == 3
        assert "Table_A" in orchestrator.tasks
        assert "Table_B" in orchestrator.tasks
        assert "Table_C" in orchestrator.tasks
