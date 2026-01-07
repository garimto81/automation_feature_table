"""vMix HTTP API client."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree

import httpx

if TYPE_CHECKING:
    from src.config.settings import VMixSettings

logger = logging.getLogger(__name__)


@dataclass
class VMixState:
    """Current vMix state."""

    recording: bool = False
    recording_duration: int = 0
    streaming: bool = False
    replay_recording: bool = False
    inputs: list[dict[str, Any]] = field(default_factory=list)


class VMixClient:
    """vMix HTTP API Client.

    Provides async methods to control vMix recording and replay functions.
    API Reference: https://www.vmix.com/help25/DeveloperAPI.html
    """

    def __init__(self, settings: "VMixSettings"):
        self.settings = settings
        self.base_url = f"http://{settings.host}:{settings.port}/api"
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.settings.timeout)
        return self._client

    async def _call_api(self, function: str, **params: str) -> bool:
        """Call vMix API function.

        Args:
            function: The vMix function name (e.g., 'StartRecording')
            **params: Additional parameters (Input, Value, Channel, etc.)

        Returns:
            True if successful, False otherwise
        """
        client = await self._ensure_client()

        query_params = {"Function": function}
        query_params.update(params)

        try:
            response = await client.get(self.base_url, params=query_params)
            if response.status_code == 200:
                logger.debug(f"vMix API success: {function} {params}")
                return True
            else:
                logger.error(f"vMix API error: {function} returned {response.status_code}")
                return False
        except httpx.TimeoutException:
            logger.error(f"vMix API timeout: {function}")
            return False
        except Exception as e:
            logger.error(f"vMix API exception: {function} - {e}")
            return False

    async def get_state(self) -> VMixState | None:
        """Get current vMix state.

        Returns:
            VMixState object or None if failed
        """
        client = await self._ensure_client()

        try:
            response = await client.get(self.base_url)
            if response.status_code == 200:
                return self._parse_state_xml(response.text)
        except Exception as e:
            logger.error(f"Failed to get vMix state: {e}")

        return None

    def _parse_state_xml(self, xml_text: str) -> VMixState:
        """Parse vMix state XML response."""
        root = ElementTree.fromstring(xml_text)

        # Parse recording state
        recording_elem = root.find(".//recording")
        recording = recording_elem is not None and recording_elem.text == "True"
        recording_duration = 0
        if recording_elem is not None:
            duration_attr = recording_elem.get("duration", "0")
            recording_duration = int(duration_attr) if duration_attr else 0

        # Parse streaming state
        streaming_elem = root.find(".//streaming")
        streaming = streaming_elem is not None and streaming_elem.text == "True"

        # Parse inputs (optional)
        inputs = []
        for input_elem in root.findall(".//input"):
            inputs.append({
                "key": input_elem.get("key", ""),
                "number": input_elem.get("number", ""),
                "type": input_elem.get("type", ""),
                "title": input_elem.get("title", ""),
                "state": input_elem.get("state", ""),
            })

        return VMixState(
            recording=recording,
            recording_duration=recording_duration,
            streaming=streaming,
            inputs=inputs,
        )

    # ============== Recording Functions ==============

    async def start_recording(self) -> bool:
        """Start recording."""
        logger.info("Starting vMix recording")
        return await self._call_api("StartRecording")

    async def stop_recording(self) -> bool:
        """Stop recording."""
        logger.info("Stopping vMix recording")
        return await self._call_api("StopRecording")

    async def toggle_recording(self) -> bool:
        """Toggle recording state."""
        return await self._call_api("StartStopRecording")

    async def is_recording(self) -> bool:
        """Check if vMix is currently recording."""
        state = await self.get_state()
        return state.recording if state else False

    # ============== Replay Functions ==============

    async def replay_start_recording(self, channel: str = "") -> bool:
        """Start replay recording.

        Args:
            channel: Replay channel (A, B, Current, or empty for default)
        """
        logger.info(f"Starting replay recording (channel: {channel or 'default'})")
        params = {}
        if channel:
            params["Channel"] = channel
        return await self._call_api("ReplayStartRecording", **params)

    async def replay_stop_recording(self, channel: str = "") -> bool:
        """Stop replay recording.

        Args:
            channel: Replay channel (A, B, Current, or empty for default)
        """
        logger.info(f"Stopping replay recording (channel: {channel or 'default'})")
        params = {}
        if channel:
            params["Channel"] = channel
        return await self._call_api("ReplayStopRecording", **params)

    async def replay_mark_in(self, channel: str = "") -> bool:
        """Mark replay in point (start of event).

        Args:
            channel: Replay channel (A, B, Current, or empty)
        """
        logger.debug(f"Marking replay IN point (channel: {channel or 'default'})")
        params = {}
        if channel:
            params["Channel"] = channel
        return await self._call_api("ReplayMarkIn", **params)

    async def replay_mark_out(self, channel: str = "") -> bool:
        """Mark replay out point (end of event).

        Args:
            channel: Replay channel (A, B, Current, or empty)
        """
        logger.debug(f"Marking replay OUT point (channel: {channel or 'default'})")
        params = {}
        if channel:
            params["Channel"] = channel
        return await self._call_api("ReplayMarkOut", **params)

    async def replay_mark_in_out(self, seconds: int, channel: str = "") -> bool:
        """Mark in/out with specified duration.

        Args:
            seconds: Duration in seconds
            channel: Replay channel
        """
        params = {"Value": str(seconds)}
        if channel:
            params["Channel"] = channel
        return await self._call_api("ReplayMarkInOut", **params)

    async def replay_mark_in_out_live(self, seconds: int) -> bool:
        """Create live replay mark with duration.

        Args:
            seconds: Duration in seconds to capture
        """
        logger.info(f"Creating live replay mark ({seconds}s)")
        return await self._call_api("ReplayMarkInOutLive", Value=str(seconds))

    async def replay_mark_cancel(self) -> bool:
        """Cancel current replay mark."""
        return await self._call_api("ReplayMarkCancel")

    async def replay_play_event(self, event_number: int = 0) -> bool:
        """Play a specific replay event.

        Args:
            event_number: Event number to play (0 for last event)
        """
        params = {}
        if event_number > 0:
            params["Value"] = str(event_number)
        return await self._call_api("ReplayPlayEvent", **params)

    async def replay_play_last_event(self) -> bool:
        """Play the last recorded replay event."""
        return await self._call_api("ReplayPlayLastEvent")

    async def replay_stop(self) -> bool:
        """Stop replay playback."""
        return await self._call_api("ReplayStopEvents")

    async def replay_export_last_event(self) -> bool:
        """Export the last replay event to a file."""
        logger.info("Exporting last replay event")
        return await self._call_api("ReplayExportLastEvent")

    # ============== Connection Management ==============

    async def close(self) -> None:
        """Close HTTP client connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("vMix client connection closed")

    async def ping(self) -> bool:
        """Check if vMix is reachable."""
        state = await self.get_state()
        return state is not None
