"""Gemini Live API integration for real-time video analysis."""

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import websockets

from src.config.settings import GeminiSettings
from src.models.hand import AIVideoResult, Card, HandRank
from src.secondary.video_capture import VideoFrame

logger = logging.getLogger(__name__)


class GeminiLiveProcessor:
    """Real-time video analysis using Gemini Live API."""

    SYSTEM_PROMPT = """You are a professional poker broadcast analyzer. \
Analyze each video frame and detect:

1. HAND BOUNDARIES:
   - hand_start: New cards being dealt, players receiving hole cards
   - hand_end: Pot being pushed to winner, cards being mucked, dealer button moving

2. CARD DETECTION:
   - Read visible community cards on the table (flop, turn, river)
   - Read player hole cards if shown on broadcast graphics overlay
   - Use standard notation: Ah (Ace of hearts), Kd (King of diamonds), etc.

3. ACTION DETECTION:
   - showdown: Multiple players revealing their cards
   - all_in: Player pushing all chips forward
   - big_pot: Significant pot size visible

4. HAND RANKING:
   - When cards are visible, identify the poker hand rank
   - Royal Flush, Straight Flush, Four of a Kind, Full House, Flush, Straight, \
Three of a Kind, Two Pair, One Pair, High Card

IMPORTANT: Respond ONLY with valid JSON in this exact format:
{
  "event": "hand_start" | "hand_end" | "showdown" | "all_in" | "action" | "none",
  "cards_detected": ["Ah", "Kd"],
  "community_cards": ["Qs", "Jc", "10h"],
  "hand_rank": "Full House" | null,
  "confidence": 0.95,
  "context": "Brief description of what you see"
}

If nothing significant is detected, use event: "none" with low confidence."""

    def __init__(self, settings: GeminiSettings, table_id: str):
        self.settings = settings
        self.table_id = table_id
        self._ws: Any = None  # WebSocket connection (type varies by websockets version)
        self._running = False
        self._session_start: datetime | None = None
        self._retry_count = 0
        self._max_retries = 3

    async def connect(self) -> None:
        """Establish WebSocket connection to Gemini Live API with retry."""
        url = f"{self.settings.ws_url}?key={self.settings.api_key}"
        logger.info(f"Connecting to Gemini Live API for {self.table_id}")

        last_error = None

        while self._retry_count < self._max_retries:
            try:
                self._ws = await websockets.connect(url)

                # Send setup message
                setup_msg = {
                    "setup": {
                        "model": f"models/{self.settings.model}",
                        "generation_config": {
                            "response_modalities": ["TEXT"],
                            "temperature": 0.1,  # Low temperature for consistent detection
                        },
                        "system_instruction": {
                            "parts": [{"text": self.SYSTEM_PROMPT}]
                        },
                    }
                }

                await self._ws.send(json.dumps(setup_msg))

                # Wait for setup confirmation
                response = await self._ws.recv()
                response_str = (
                    response.decode("utf-8") if isinstance(response, bytes) else response
                )
                logger.debug(f"Setup response: {response_str}")

                self._session_start = datetime.now()
                logger.info(f"Connected to Gemini Live API for {self.table_id}")

                # Reset retry count on success
                self._retry_count = 0
                return

            except Exception as e:
                last_error = e
                self._retry_count += 1

                if self._retry_count < self._max_retries:
                    delay = self._get_backoff_delay()
                    logger.warning(
                        f"Connection failed "
                        f"(attempt {self._retry_count}/{self._max_retries}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Failed to connect after {self._max_retries} attempts: {e}")

        # All retries exhausted
        if last_error:
            raise last_error

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info(f"Disconnected from Gemini Live API for {self.table_id}")

    def _should_reconnect(self) -> bool:
        """Check if session timeout is approaching."""
        if not self._session_start:
            return True

        elapsed = (datetime.now() - self._session_start).total_seconds()
        # Reconnect 30 seconds before timeout
        return elapsed >= (self.settings.session_timeout - 30)

    def _get_backoff_delay(self) -> float:
        """
        Calculate exponential backoff delay.

        Returns:
            Delay in seconds (1, 2, 4, 8 max)
        """
        delay = min(2 ** self._retry_count, 8.0)
        return float(delay)

    async def _ensure_connection(self) -> None:
        """Ensure connection is active, reconnect if needed."""
        if not self._ws or self._should_reconnect():
            if self._ws:
                await self.disconnect()
            await self.connect()

    async def analyze_frame(self, frame: VideoFrame) -> AIVideoResult | None:
        """
        Analyze a single video frame.

        Args:
            frame: VideoFrame to analyze

        Returns:
            AIVideoResult or None if analysis failed
        """
        await self._ensure_connection()

        try:
            # Encode frame to base64 JPEG (quality 80 for balance)
            jpeg_bytes = frame.to_jpeg(quality=80)
            frame_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

            # Send frame for analysis
            msg = {
                "realtime_input": {
                    "media_chunks": [
                        {
                            "mime_type": "image/jpeg",
                            "data": frame_b64,
                        }
                    ]
                }
            }

            await self._ws.send(json.dumps(msg))

            # Receive response
            response = await asyncio.wait_for(
                self._ws.recv(),
                timeout=5.0,
            )

            return self._parse_response(response, frame.timestamp)

        except TimeoutError:
            logger.warning(f"Timeout waiting for Gemini response for {self.table_id}")
            return None
        except Exception as e:
            logger.error(f"Error analyzing frame: {e}")
            return None

    def _parse_response(
        self,
        response: str,
        timestamp: datetime,
    ) -> AIVideoResult | None:
        """Parse Gemini API response into AIVideoResult."""
        try:
            data = json.loads(response)

            # Extract text from response structure
            # Structure: serverContent.modelTurn.parts[0].text
            text = (
                data.get("serverContent", {})
                .get("modelTurn", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            if not text:
                return None

            # Parse JSON from text
            result_json = json.loads(text)

            # Skip "none" events with low confidence
            event = result_json.get("event", "none")
            confidence = result_json.get("confidence", 0.0)

            if event == "none" and confidence < 0.5:
                return None

            # Parse detected cards
            detected_cards = []
            for card_str in result_json.get("cards_detected", []):
                try:
                    detected_cards.append(Card.from_string(card_str))
                except ValueError:
                    pass

            # Parse hand rank
            hand_rank = None
            rank_str = result_json.get("hand_rank")
            if rank_str:
                rank_name = rank_str.upper().replace(" ", "_")
                try:
                    hand_rank = HandRank[rank_name]
                except KeyError:
                    pass

            return AIVideoResult(
                table_id=self.table_id,
                detected_event=event,
                detected_cards=detected_cards,
                hand_rank=hand_rank,
                confidence=confidence,
                context=result_json.get("context", ""),
                timestamp=timestamp,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Gemini response: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return None

    async def process_stream(
        self,
        frames: AsyncIterator[VideoFrame],
    ) -> AsyncIterator[AIVideoResult]:
        """
        Process a stream of video frames.

        Args:
            frames: AsyncIterator of VideoFrame objects

        Yields:
            AIVideoResult for significant detections
        """
        self._running = True

        async for frame in frames:
            if not self._running:
                break

            result = await self.analyze_frame(frame)

            if result and result.confidence >= self.settings.confidence_threshold:
                logger.info(
                    f"[{self.table_id}] Detected: {result.detected_event} "
                    f"(confidence: {result.confidence:.2f})"
                )
                yield result

    def stop(self) -> None:
        """Stop processing."""
        self._running = False
