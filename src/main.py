"""Main application entry point - Database and Recording focused version."""

import asyncio
import logging
import signal
from datetime import datetime

from src.config.settings import PokerGFXSettings, Settings, get_settings
from src.database.connection import DatabaseManager
from src.database.repository import HandRepository
from src.fallback.detector import AutomationState, FailureDetector, FailureReason
from src.fallback.manual_marker import MultiTableManualMarker, PairedMark
from src.fusion.engine import MultiTableFusionEngine
from src.grading.grader import HandGrader
from src.models.hand import AIVideoResult, FusedHandResult, HandResult
from src.primary.json_file_watcher import JSONFileWatcher
from src.primary.pokergfx_client import PokerGFXClient
from src.recording.manager import RecordingManager
from src.recording.session import RecordingSession
from src.secondary.gemini_live import GeminiLiveProcessor
from src.secondary.video_capture import VideoCapture
from src.vmix.client import VMixClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Type alias for Primary source (WebSocket or JSON file watcher)
PrimarySource = PokerGFXClient | JSONFileWatcher


def create_primary_source(settings: PokerGFXSettings) -> PrimarySource:
    """Factory function to create Primary source based on mode setting.

    Args:
        settings: PokerGFX settings with mode configured

    Returns:
        PokerGFXClient for websocket mode, JSONFileWatcher for json mode

    Raises:
        ValueError: If mode is not recognized
    """
    mode = settings.mode.lower()

    if mode == "websocket":
        logger.info("Using WebSocket mode for Primary source")
        return PokerGFXClient(settings)
    elif mode == "json":
        if not settings.json_watch_path:
            raise ValueError("POKERGFX_JSON_PATH must be set for json mode")
        logger.info(f"Using JSON file mode for Primary source: {settings.json_watch_path}")
        return JSONFileWatcher(settings)
    else:
        raise ValueError(f"Unknown POKERGFX_MODE: {mode}. Use 'websocket' or 'json'")


class PokerHandCaptureSystem:
    """Main system orchestrating all components.

    Responsibilities:
    - Coordinate Primary (PokerGFX) and Secondary (Gemini) sources
    - Fuse results and determine hand quality
    - Control vMix recording per hand
    - Grade hands and save to database
    - Handle fallback when automation fails
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._running = False

        # Database
        self.db_manager = DatabaseManager(self.settings.database)
        self.hand_repository = HandRepository(self.db_manager)

        # Primary source (WebSocket or JSON file watcher based on mode)
        self.primary_source: PrimarySource = create_primary_source(self.settings.pokergfx)

        # Secondary sources
        self.video_capture = VideoCapture(self.settings.video)
        self.gemini_processors: dict[str, GeminiLiveProcessor] = {}

        # Fusion engine
        self.fusion_engine = MultiTableFusionEngine(
            table_ids=self.settings.table_ids,
            secondary_confidence_threshold=self.settings.gemini.confidence_threshold,
        )

        # vMix and Recording
        self.vmix_client = VMixClient(self.settings.vmix)
        self.recording_manager: RecordingManager | None = None

        # Grading
        self.grader = HandGrader.from_settings(self.settings.grading)

        # Fallback
        self.failure_detector = FailureDetector.from_settings(
            self.settings.fallback,
            on_fallback_triggered=self._on_fallback_triggered,
            on_fallback_reset=self._on_fallback_reset,
        )
        self.manual_markers = MultiTableManualMarker(
            on_hand_completed=self._on_manual_hand_completed,
        )

        # Result buffers for fusion
        self._primary_buffer: dict[str, HandResult] = {}
        self._secondary_buffer: dict[str, AIVideoResult] = {}

        # Hand timing tracking
        self._hand_start_times: dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the capture system."""
        logger.info("Starting Poker Hand Capture System (DB Mode)...")
        self._running = True

        # Connect to database
        await self.db_manager.connect()
        await self.db_manager.create_tables()

        # Initialize recording manager
        self.recording_manager = RecordingManager(
            settings=self.settings.recording,
            vmix_client=self.vmix_client,
            on_recording_complete=self._on_recording_complete,
        )

        # Check vMix connection
        if await self.vmix_client.ping():
            logger.info("vMix connection established")
        else:
            logger.warning("vMix not reachable - recording will be disabled")

        # Initialize video streams and Gemini processors
        for i, stream_url in enumerate(self.settings.video.streams):
            table_id = (
                self.settings.table_ids[i]
                if i < len(self.settings.table_ids)
                else f"table_{i}"
            )
            self.video_capture.add_stream(table_id, stream_url)
            self.gemini_processors[table_id] = GeminiLiveProcessor(
                self.settings.gemini,
                table_id,
            )

        logger.info(f"Initialized {len(self.settings.video.streams)} video streams")
        logger.info("System ready")

    async def stop(self) -> None:
        """Stop the capture system."""
        logger.info("Stopping Poker Hand Capture System...")
        self._running = False

        # Stop all active recordings
        if self.recording_manager:
            await self.recording_manager.stop_all()

        # Disconnect components
        await self.primary_source.disconnect()
        self.video_capture.release_all()
        await self.vmix_client.close()

        for processor in self.gemini_processors.values():
            await processor.disconnect()

        # Disconnect database
        await self.db_manager.disconnect()

        # Log final stats
        stats = self.fusion_engine.get_aggregate_stats()
        logger.info(f"Final fusion statistics: {stats}")

        if self.recording_manager:
            rec_stats = self.recording_manager.get_stats()
            logger.info(f"Final recording statistics: {rec_stats}")

    async def _handle_hand_start(self, table_id: str, hand_number: int) -> None:
        """Handle hand start event."""
        logger.info(f"Hand started: {table_id} #{hand_number}")

        # Track start time
        self._hand_start_times[table_id] = datetime.now()

        # Start recording if vMix is available
        if self.recording_manager and self.settings.vmix.auto_record:
            await self.recording_manager.start_recording(table_id, hand_number)

        # Update failure detector
        self.failure_detector.update_primary_status(connected=True, event_received=True)

    async def _handle_primary_result(self, result: HandResult) -> None:
        """Handle result from Primary (PokerGFX)."""
        table_id = result.table_id

        # Update failure detector
        self.failure_detector.update_primary_status(connected=True, event_received=True)

        # Check for matching secondary result
        secondary = self._secondary_buffer.pop(table_id, None)

        # Fuse results
        fused = self.fusion_engine.fuse(table_id, result, secondary)

        # Track fusion match/mismatch
        if secondary:
            if fused.cross_validated:
                self.failure_detector.record_fusion_match()
            else:
                self.failure_detector.record_fusion_mismatch()

        await self._process_fused_result(fused)

    async def _handle_secondary_result(self, result: AIVideoResult) -> None:
        """Handle result from Secondary (AI Video)."""
        table_id = result.table_id

        # Update failure detector
        self.failure_detector.update_secondary_status(
            connected=True,
            event_received=True,
            confidence=result.confidence,
        )

        # Handle hand events
        if result.detected_event == "hand_start":
            # Only use for timing if primary didn't catch it
            if table_id not in self._hand_start_times:
                self._hand_start_times[table_id] = result.timestamp
        elif result.detected_event == "hand_end":
            primary = self._primary_buffer.pop(table_id, None)

            if primary:
                fused = self.fusion_engine.fuse(table_id, primary, result)
                await self._process_fused_result(fused)
            else:
                # Store for later fusion
                self._secondary_buffer[table_id] = result
        else:
            # Store for context
            self._secondary_buffer[table_id] = result

    async def _process_fused_result(self, result: FusedHandResult) -> None:
        """Process fused result - stop recording, grade, and save to DB."""
        table_id = result.table_id

        # Calculate duration
        start_time = self._hand_start_times.pop(table_id, None)
        duration_seconds = 0
        if start_time:
            duration_seconds = int((datetime.now() - start_time).total_seconds())

        # Stop recording
        if self.recording_manager:
            await self.recording_manager.stop_recording(table_id)

        # Grade the hand
        grade_result = self.grader.grade(
            hand_rank=result.hand_rank,
            duration_seconds=duration_seconds,
        )

        # Save to database
        try:
            hand_record = await self.hand_repository.save_hand(result, grade_result)
            logger.info(
                f"Saved hand {table_id} #{result.hand_number} to DB "
                f"(id={hand_record.id}, grade={grade_result.grade})"
            )
        except Exception as e:
            logger.error(f"Failed to save hand to DB: {e}")

        # Log broadcast-eligible hands
        if grade_result.broadcast_eligible:
            logger.info(
                f"BROADCAST ELIGIBLE: {table_id} #{result.hand_number} - "
                f"Grade {grade_result.grade}, {result.rank_name} "
                f"(duration: {duration_seconds}s)"
            )

        # Log premium hands
        if result.is_premium:
            logger.info(
                f"PREMIUM HAND: {table_id} #{result.hand_number} - "
                f"{result.rank_name} (source: {result.source.value})"
            )

    def _on_recording_complete(self, session: RecordingSession) -> None:
        """Handle recording completion callback."""
        logger.debug(
            f"Recording completed: {session.table_id} #{session.hand_number} "
            f"({session.duration_seconds}s)"
        )

    def _on_fallback_triggered(
        self, reason: FailureReason, state: AutomationState
    ) -> None:
        """Handle fallback trigger callback."""
        logger.warning(
            f"Fallback mode activated: {reason.value}. "
            "Manual marking is now available."
        )
        # UI should show manual marking controls here

    def _on_fallback_reset(self) -> None:
        """Handle fallback reset callback."""
        logger.info("Fallback mode deactivated. Automation resumed.")

    async def _on_manual_hand_completed(self, paired_mark: PairedMark) -> None:
        """Handle manual hand completion."""
        logger.info(
            f"Manual hand completed: {paired_mark.table_id} "
            f"(duration: {paired_mark.duration_seconds}s)"
        )
        # Save manual mark to database
        try:
            await self.hand_repository.save_manual_mark(
                table_id=paired_mark.table_id,
                mark_type="hand_end",
                marked_at=paired_mark.end_mark.marked_at,
                fallback_reason=paired_mark.end_mark.fallback_reason,
                marked_by=paired_mark.end_mark.marked_by,
            )
        except Exception as e:
            logger.error(f"Failed to save manual mark: {e}")

    async def run_primary_loop(self) -> None:
        """Run Primary (PokerGFX/JSON file) processing loop."""
        try:
            async for result in self.primary_source.listen():
                if not self._running:
                    break

                # Track hand start
                if result.table_id not in self._hand_start_times:
                    await self._handle_hand_start(result.table_id, result.hand_number)

                await self._handle_primary_result(result)
        except Exception as e:
            logger.error(f"Primary loop error: {e}")
            self.failure_detector.update_primary_status(connected=False)

    async def run_secondary_loop(self, table_id: str) -> None:
        """Run Secondary (AI Video) processing loop for a table."""
        processor = self.gemini_processors.get(table_id)
        if not processor:
            logger.warning(f"No Gemini processor for {table_id}")
            return

        try:
            frames = self.video_capture.stream_frames(table_id)
            async for result in processor.process_stream(frames):
                if not self._running:
                    break
                await self._handle_secondary_result(result)
        except Exception as e:
            logger.error(f"Secondary loop error for {table_id}: {e}")
            self.failure_detector.update_secondary_status(connected=False)

    async def run_timeout_checker(self) -> None:
        """Run periodic timeout checker."""
        while self._running:
            await asyncio.sleep(10)  # Check every 10 seconds

            if self._running:
                reason = self.failure_detector.check_timeouts()
                if reason and self.settings.fallback.enabled:
                    logger.warning(f"Timeout detected: {reason.value}")
                    # Fallback will be triggered by detector

    async def run(self) -> None:
        """Run the main processing loops."""
        await self.start()

        try:
            # Create tasks for all processing loops
            tasks = [
                asyncio.create_task(self.run_primary_loop()),
                asyncio.create_task(self.run_timeout_checker()),
            ]

            # Add secondary loops for each table
            for table_id in self.gemini_processors:
                tasks.append(asyncio.create_task(self.run_secondary_loop(table_id)))

            # Wait for all tasks
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Tasks cancelled")
        finally:
            await self.stop()

    # ============== Manual Marking API ==============

    def mark_hand_start(
        self, table_id: str, operator: str | None = None
    ) -> None:
        """Manually mark hand start (for Plan B)."""
        if not self.failure_detector.is_fallback_active:
            logger.warning("Manual marking only available in fallback mode")
            return

        marker = self.manual_markers.get_marker(
            table_id, self.failure_detector.state.to_dict().get("last_failure_reason")
        )
        marker.mark_hand_start(operator)

    def mark_hand_end(
        self, table_id: str, operator: str | None = None
    ) -> None:
        """Manually mark hand end (for Plan B)."""
        if not self.failure_detector.is_fallback_active:
            logger.warning("Manual marking only available in fallback mode")
            return

        marker = self.manual_markers.get_marker(table_id)
        marker.mark_hand_end(operator)

    def get_system_stats(self) -> dict:
        """Get comprehensive system statistics."""
        stats = {
            "fusion": self.fusion_engine.get_aggregate_stats(),
            "fallback": self.failure_detector.get_stats(),
            "manual_markers": self.manual_markers.get_all_stats(),
            "primary_mode": self.settings.pokergfx.mode,
        }

        if self.recording_manager:
            stats["recording"] = self.recording_manager.get_stats()

        # Add primary source specific stats
        if hasattr(self.primary_source, "get_stats"):
            stats["primary_source"] = self.primary_source.get_stats()

        return stats


async def main() -> None:
    """Main entry point."""
    settings = get_settings()

    # Configure logging level
    logging.getLogger().setLevel(settings.log_level)

    system = PokerHandCaptureSystem(settings)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def shutdown_handler():
        logger.info("Shutdown signal received")
        system._running = False

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
