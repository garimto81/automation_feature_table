"""Video capture from RTSP/NDI streams."""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np

from src.config.settings import VideoSettings

logger = logging.getLogger(__name__)


@dataclass
class VideoFrame:
    """Captured video frame with metadata."""

    table_id: str
    frame: np.ndarray
    timestamp: datetime
    frame_number: int

    def to_jpeg(self, quality: int = 80) -> bytes:
        """Encode frame to JPEG bytes."""
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, buffer = cv2.imencode(".jpg", self.frame, encode_params)
        return buffer.tobytes()


class VideoCapture:
    """Video capture handler for multiple streams."""

    def __init__(self, settings: VideoSettings):
        self.settings = settings
        self._captures: dict[str, cv2.VideoCapture] = {}
        self._running = False
        self._frame_counts: dict[str, int] = {}
        self._buffers: dict[str, deque] = {}
        self._target_width = 640  # Optimize for API cost/quality balance

    def add_stream(self, table_id: str, url: str) -> bool:
        """
        Add a video stream for capture.

        Args:
            table_id: Identifier for the table
            url: RTSP or NDI URL

        Returns:
            True if stream opened successfully
        """
        try:
            cap = cv2.VideoCapture(url)

            if not cap.isOpened():
                logger.error(f"Failed to open stream for {table_id}: {url}")
                return False

            # Configure capture
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency

            self._captures[table_id] = cap
            self._frame_counts[table_id] = 0
            self._buffers[table_id] = deque(maxlen=self.settings.buffer_size)

            logger.info(f"Added stream for {table_id}: {url}")
            return True

        except Exception as e:
            logger.error(f"Error adding stream for {table_id}: {e}")
            return False

    def remove_stream(self, table_id: str) -> None:
        """Remove and release a video stream."""
        if table_id in self._captures:
            self._captures[table_id].release()
            del self._captures[table_id]
            del self._frame_counts[table_id]
            del self._buffers[table_id]
            logger.info(f"Removed stream for {table_id}")

    def _resize_frame(
        self,
        frame: np.ndarray,
        target_width: int | None = None
    ) -> np.ndarray:
        """
        Resize frame for optimization (only downscale, never upscale).

        Args:
            frame: Input frame
            target_width: Target width (default: 640)

        Returns:
            Resized frame or original if already smaller
        """
        target_width = target_width or self._target_width
        height, width = frame.shape[:2]

        # Don't upscale
        if width <= target_width:
            return frame

        # Calculate new dimensions maintaining aspect ratio
        scale = target_width / width
        new_height = int(height * scale)

        # Resize with high-quality interpolation
        resized = cv2.resize(
            frame,
            (target_width, new_height),
            interpolation=cv2.INTER_AREA
        )

        return resized

    def capture_frame(self, table_id: str) -> VideoFrame | None:
        """
        Capture a single frame from a stream.

        Args:
            table_id: Table identifier

        Returns:
            VideoFrame or None if capture failed
        """
        if table_id not in self._captures:
            logger.warning(f"No stream registered for {table_id}")
            return None

        cap = self._captures[table_id]
        ret, frame = cap.read()

        if not ret:
            logger.warning(f"Failed to read frame from {table_id}")
            return None

        # Resize frame for optimization
        frame = self._resize_frame(frame)

        self._frame_counts[table_id] += 1

        video_frame = VideoFrame(
            table_id=table_id,
            frame=frame,
            timestamp=datetime.now(),
            frame_number=self._frame_counts[table_id],
        )

        # Add to buffer
        self._buffers[table_id].append(video_frame)

        return video_frame

    async def stream_frames(
        self,
        table_id: str,
        fps: int | None = None,
    ) -> AsyncIterator[VideoFrame]:
        """
        Stream frames at specified FPS.

        Args:
            table_id: Table identifier
            fps: Frames per second (default from settings)

        Yields:
            VideoFrame objects
        """
        fps = fps or self.settings.fps
        interval = 1.0 / fps
        self._running = True

        logger.info(f"Starting frame stream for {table_id} at {fps} FPS")

        while self._running:
            frame = self.capture_frame(table_id)

            if frame:
                yield frame

            await asyncio.sleep(interval)

    async def stream_all_tables(
        self,
        fps: int | None = None,
    ) -> AsyncIterator[VideoFrame]:
        """
        Stream frames from all registered tables.

        Yields frames in round-robin fashion.
        """
        fps = fps or self.settings.fps
        interval = 1.0 / fps / max(len(self._captures), 1)
        self._running = True

        logger.info(f"Starting frame stream for {len(self._captures)} tables")

        table_ids = list(self._captures.keys())

        while self._running:
            for table_id in table_ids:
                if not self._running:
                    break

                frame = self.capture_frame(table_id)
                if frame:
                    yield frame

                await asyncio.sleep(interval)

    def stop(self) -> None:
        """Stop all streaming."""
        self._running = False

    def release_all(self) -> None:
        """Release all video captures."""
        self.stop()
        for table_id in list(self._captures.keys()):
            self.remove_stream(table_id)
        logger.info("Released all video captures")

    def get_latest_frame(self, table_id: str) -> VideoFrame | None:
        """Get the most recent frame from buffer."""
        if table_id in self._buffers and self._buffers[table_id]:
            return self._buffers[table_id][-1]
        return None

    def get_stream_info(self, table_id: str) -> dict | None:
        """Get information about a stream."""
        if table_id not in self._captures:
            return None

        cap = self._captures[table_id]
        return {
            "table_id": table_id,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "frame_count": self._frame_counts.get(table_id, 0),
            "buffer_size": len(self._buffers.get(table_id, [])),
        }
