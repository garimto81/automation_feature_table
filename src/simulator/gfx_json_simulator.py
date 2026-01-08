"""GFX JSON Simulator for NAS testing.

Simulates real-time hand generation by creating cumulative JSON files
at specified intervals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from src.simulator.config import SimulatorSettings, get_simulator_settings
from src.simulator.hand_splitter import HandSplitter

logger = logging.getLogger(__name__)


class Status(Enum):
    """Simulator status."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class LogEntry:
    """Log entry for simulator events."""

    timestamp: datetime
    level: str
    message: str
    table_name: str = ""

    @property
    def icon(self) -> str:
        """Get icon based on log level."""
        icons = {
            "INFO": "OK",
            "WARNING": "WARN",
            "ERROR": "ERR",
            "SUCCESS": "OK",
        }
        return icons.get(self.level, "INFO")

    def __str__(self) -> str:
        """Format log entry as string."""
        ts = self.timestamp.strftime("%H:%M:%S")
        table = f" ({self.table_name})" if self.table_name else ""
        return f"[{ts}] {self.icon} {self.message}{table}"


@dataclass
class SimulationProgress:
    """Progress tracking for simulation."""

    current_hand: int = 0
    total_hands: int = 0
    start_time: datetime | None = None
    current_file: str = ""

    @property
    def progress(self) -> float:
        """Get progress as percentage (0.0 to 1.0)."""
        if self.total_hands == 0:
            return 0.0
        return self.current_hand / self.total_hands

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def remaining_seconds(self) -> float:
        """Estimate remaining time in seconds."""
        if self.current_hand == 0 or self.total_hands == 0:
            return 0.0
        elapsed = self.elapsed_seconds
        rate = elapsed / self.current_hand
        remaining_hands = self.total_hands - self.current_hand
        return rate * remaining_hands


@dataclass
class GFXJsonSimulator:
    """Simulator for generating cumulative GFX JSON files."""

    source_path: Path
    target_path: Path
    interval: int = 60
    settings: SimulatorSettings = field(default_factory=get_simulator_settings)

    # State
    status: Status = field(default=Status.IDLE, init=False)
    progress: SimulationProgress = field(
        default_factory=SimulationProgress, init=False
    )
    logs: list[LogEntry] = field(default_factory=list, init=False)
    _stop_requested: bool = field(default=False, init=False)
    _selected_files: list[Path] = field(default_factory=list, init=False)

    def _log(
        self,
        message: str,
        level: str = "INFO",
        table_name: str = "",
    ) -> None:
        """Add log entry."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            table_name=table_name,
        )
        self.logs.append(entry)
        # Keep only last 100 logs
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]

        # Also log to console
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(str(entry))

    def stop(self) -> None:
        """Request simulation stop."""
        self._stop_requested = True
        self.status = Status.STOPPED
        self._log("Simulation stopped by user", "WARNING")

    def get_logs(self, limit: int = 20) -> list[LogEntry]:
        """Get recent logs."""
        return self.logs[-limit:]

    def _write_with_retry(self, path: Path, content: str) -> bool:
        """Write file with retry logic.

        Args:
            path: Target file path
            content: File content

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(1, self.settings.retry_count + 1):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return True
            except OSError as e:
                self._log(
                    f"Write failed (attempt {attempt}/{self.settings.retry_count}): {e}",
                    "WARNING",
                )
                if attempt < self.settings.retry_count:
                    time.sleep(self.settings.retry_delay_sec)

        self._log(f"Failed to write after {self.settings.retry_count} attempts", "ERROR")
        return False

    def _discover_json_files(self) -> list[Path]:
        """Discover all JSON files in source directory."""
        json_files = list(self.source_path.rglob("*.json"))
        self._log(f"Found {len(json_files)} JSON files in {self.source_path}")
        return json_files

    async def simulate_file(self, json_path: Path) -> bool:
        """Simulate single JSON file.

        Args:
            json_path: Path to source JSON file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read and parse JSON
            data = json.loads(json_path.read_text(encoding="utf-8"))
            hands = HandSplitter.split_hands(data)
            metadata = HandSplitter.extract_metadata(data)

            if not hands:
                self._log(f"No hands found in {json_path.name}", "WARNING")
                return True

            # Determine relative path for output
            rel_path = json_path.relative_to(self.source_path)
            output_path = self.target_path / rel_path

            # Extract table name from path
            parts = rel_path.parts
            table_name = parts[0] if parts else ""

            self._log(f"Starting simulation: {rel_path} ({len(hands)} hands)", table_name=table_name)

            # Simulate each hand
            for i in range(1, len(hands) + 1):
                if self._stop_requested:
                    return False

                # Build cumulative JSON
                cumulative = HandSplitter.build_cumulative(hands, i, metadata)
                content = json.dumps(cumulative, indent=2, ensure_ascii=False)

                # Write to target
                if not self._write_with_retry(output_path, content):
                    self.status = Status.ERROR
                    return False

                self.progress.current_hand += 1
                self._log(f"Hand {i}/{len(hands)} generated", "SUCCESS", table_name)

                # Wait for interval (except last hand)
                if i < len(hands):
                    await asyncio.sleep(self.interval)

            self._log(f"Completed: {rel_path}", "SUCCESS", table_name)
            return True

        except json.JSONDecodeError as e:
            self._log(f"JSON parse error in {json_path.name}: {e}", "ERROR")
            return False
        except Exception as e:
            self._log(f"Error processing {json_path.name}: {e}", "ERROR")
            return False

    async def run(self) -> None:
        """Run simulation for all discovered JSON files."""
        self._stop_requested = False
        self.status = Status.RUNNING
        self.progress = SimulationProgress(start_time=datetime.now())

        self._log("Starting GFX JSON Simulator")
        self._log(f"Source: {self.source_path}")
        self._log(f"Target: {self.target_path}")
        self._log(f"Interval: {self.interval}s")

        # Use selected files if provided, otherwise discover
        if self._selected_files:
            json_files = self._selected_files
            self._log(f"Using {len(json_files)} selected files")
        else:
            json_files = self._discover_json_files()

        if not json_files:
            self._log("No JSON files found", "WARNING")
            self.status = Status.COMPLETED
            return

        # Calculate total hands
        total_hands = 0
        for json_path in json_files:
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                total_hands += HandSplitter.get_hand_count(data)
            except Exception:
                pass

        self.progress.total_hands = total_hands
        self._log(f"Total hands to process: {total_hands}")

        # Process each file
        for json_path in json_files:
            if self._stop_requested:
                break

            self.progress.current_file = json_path.name
            success = await self.simulate_file(json_path)

            if not success and self.status == Status.ERROR:
                break

        if not self._stop_requested and self.status != Status.ERROR:
            self.status = Status.COMPLETED
            self._log("Simulation completed successfully", "SUCCESS")

    def run_sync(self) -> None:
        """Run simulation synchronously (for CLI)."""
        asyncio.run(self.run())


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="GFX JSON Simulator for NAS testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--source",
        type=Path,
        default=Path("gfx_json"),
        help="Source directory containing GFX JSON files (default: gfx_json)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Target directory for output files (NAS path)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between hand generations in seconds (default: 60)",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in CLI mode without Streamlit GUI",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    """Main entry point for CLI."""
    args = parse_args()
    setup_logging(args.verbose)

    if not args.no_gui:
        # Launch Streamlit
        import subprocess
        gui_path = Path(__file__).parent / "gui" / "app.py"
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", str(gui_path),
            "--",
            "--source", str(args.source),
            "--target", str(args.target),
            "--interval", str(args.interval),
        ])
        return 0

    # CLI mode
    if not args.source.exists():
        logger.error(f"Source directory not found: {args.source}")
        return 1

    simulator = GFXJsonSimulator(
        source_path=args.source,
        target_path=args.target,
        interval=args.interval,
    )

    try:
        simulator.run_sync()
        return 0 if simulator.status == Status.COMPLETED else 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        simulator.stop()
        return 130


if __name__ == "__main__":
    sys.exit(main())
