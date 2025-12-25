"""Main application entry point."""

import asyncio
import logging
import signal
from typing import Optional

from src.config.settings import Settings, get_settings
from src.fusion.engine import MultiTableFusionEngine
from src.models.hand import AIVideoResult, FusedHandResult, HandResult
from src.output.clip_marker import ClipMarkerManager
from src.output.overlay import OverlayServer
from src.primary.pokergfx_client import PokerGFXClient
from src.secondary.gemini_live import GeminiLiveProcessor
from src.secondary.video_capture import VideoCapture

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class PokerHandCaptureSystem:
    """Main system orchestrating all components."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._running = False

        # Initialize components
        self.pokergfx_client = PokerGFXClient(self.settings.pokergfx)
        self.video_capture = VideoCapture(self.settings.video)
        self.fusion_engine = MultiTableFusionEngine(
            table_ids=self.settings.table_ids,
            secondary_confidence_threshold=self.settings.gemini.confidence_threshold,
        )
        self.overlay_server = OverlayServer(self.settings.output)
        self.clip_marker = ClipMarkerManager(self.settings.output)

        # Gemini processors per table
        self.gemini_processors: dict[str, GeminiLiveProcessor] = {}

        # Result buffers for fusion
        self._primary_buffer: dict[str, HandResult] = {}
        self._secondary_buffer: dict[str, AIVideoResult] = {}

    async def start(self) -> None:
        """Start the capture system."""
        logger.info("Starting Poker Hand Capture System...")
        self._running = True

        # Start overlay server
        await self.overlay_server.start()

        # Initialize video streams
        for i, stream_url in enumerate(self.settings.video.streams):
            table_id = self.settings.table_ids[i] if i < len(self.settings.table_ids) else f"table_{i}"
            self.video_capture.add_stream(table_id, stream_url)

            # Initialize Gemini processor for each table
            self.gemini_processors[table_id] = GeminiLiveProcessor(
                self.settings.gemini,
                table_id,
            )

        logger.info(f"Initialized {len(self.settings.video.streams)} video streams")

    async def stop(self) -> None:
        """Stop the capture system."""
        logger.info("Stopping Poker Hand Capture System...")
        self._running = False

        # Stop components
        await self.pokergfx_client.disconnect()
        self.video_capture.release_all()
        await self.overlay_server.stop()

        # Disconnect Gemini processors
        for processor in self.gemini_processors.values():
            await processor.disconnect()

        # Export final markers
        if self.clip_marker.markers:
            self.clip_marker.export_json()
            self.clip_marker.export_edl()

        # Log final stats
        stats = self.fusion_engine.get_aggregate_stats()
        logger.info(f"Final statistics: {stats}")

    async def _handle_primary_result(self, result: HandResult) -> None:
        """Handle result from Primary (PokerGFX)."""
        table_id = result.table_id

        # Check for matching secondary result
        secondary = self._secondary_buffer.pop(table_id, None)

        # Fuse results
        fused = self.fusion_engine.fuse(table_id, result, secondary)

        await self._process_fused_result(fused)

    async def _handle_secondary_result(self, result: AIVideoResult) -> None:
        """Handle result from Secondary (AI Video)."""
        table_id = result.table_id

        # Store in buffer for fusion with primary
        # If it's a hand_end event, try to fuse
        if result.detected_event == "hand_end":
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
        """Process fused result - broadcast and mark."""
        # Broadcast to overlay clients
        await self.overlay_server.broadcast_hand_result(result)

        # Add clip marker
        self.clip_marker.add_from_result(result)

        # Log premium hands
        if result.is_premium:
            logger.info(
                f"PREMIUM HAND: {result.table_id} #{result.hand_number} - "
                f"{result.rank_name} (source: {result.source.value})"
            )

    async def run_primary_loop(self) -> None:
        """Run Primary (PokerGFX) processing loop."""
        try:
            async for result in self.pokergfx_client.listen():
                if not self._running:
                    break
                await self._handle_primary_result(result)
        except Exception as e:
            logger.error(f"Primary loop error: {e}")

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

    async def run(self) -> None:
        """Run the main processing loops."""
        await self.start()

        try:
            # Create tasks for all processing loops
            tasks = [
                asyncio.create_task(self.run_primary_loop()),
            ]

            # Add secondary loops for each table
            for table_id in self.gemini_processors:
                tasks.append(
                    asyncio.create_task(self.run_secondary_loop(table_id))
                )

            # Wait for all tasks
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Tasks cancelled")
        finally:
            await self.stop()


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
        loop.add_signal_handler(sig, shutdown_handler)

    await system.run()


if __name__ == "__main__":
    asyncio.run(main())
