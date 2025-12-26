"""Tests for vMix API client module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.vmix.client import VMixClient, VMixState
from src.vmix.replay_controller import HandRecordingResult, ReplayController


class TestVMixClient:
    """Test cases for VMixClient."""

    def setup_method(self):
        """Set up test fixtures."""
        self.settings = MagicMock()
        self.settings.host = "127.0.0.1"
        self.settings.port = 8088
        self.settings.timeout = 5.0
        self.client = VMixClient(self.settings)

    @pytest.mark.asyncio
    async def test_base_url_construction(self):
        """Test that base URL is correctly constructed."""
        assert self.client.base_url == "http://127.0.0.1:8088/api"

    @pytest.mark.asyncio
    async def test_call_api_success(self):
        """Test successful API call."""
        with patch.object(self.client, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_ensure.return_value = mock_client

            result = await self.client._call_api("StartRecording")

            assert result is True
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_api_failure(self):
        """Test failed API call."""
        with patch.object(self.client, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.get.return_value = mock_response
            mock_ensure.return_value = mock_client

            result = await self.client._call_api("StartRecording")

            assert result is False

    @pytest.mark.asyncio
    async def test_start_recording(self):
        """Test start recording API call."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.start_recording()

            assert result is True
            mock_call.assert_called_once_with("StartRecording")

    @pytest.mark.asyncio
    async def test_stop_recording(self):
        """Test stop recording API call."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.stop_recording()

            assert result is True
            mock_call.assert_called_once_with("StopRecording")

    @pytest.mark.asyncio
    async def test_replay_mark_in(self):
        """Test replay mark in API call."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_mark_in()

            assert result is True
            mock_call.assert_called_once_with("ReplayMarkIn")

    @pytest.mark.asyncio
    async def test_replay_mark_out(self):
        """Test replay mark out API call."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_mark_out()

            assert result is True
            mock_call.assert_called_once_with("ReplayMarkOut")

    @pytest.mark.asyncio
    async def test_replay_mark_with_channel(self):
        """Test replay mark with channel parameter."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            await self.client.replay_mark_in(channel="A")

            mock_call.assert_called_once_with("ReplayMarkIn", Channel="A")

    @pytest.mark.asyncio
    async def test_replay_export_last_event(self):
        """Test replay export last event API call."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_export_last_event()

            assert result is True
            mock_call.assert_called_once_with("ReplayExportLastEvent")

    def test_parse_state_xml(self):
        """Test parsing vMix state XML."""
        xml_text = """<?xml version="1.0" encoding="utf-8"?>
        <vmix>
            <recording duration="123">True</recording>
            <streaming>False</streaming>
            <inputs>
                <input key="abc" number="1" type="Video" title="Camera 1" state="Running"/>
            </inputs>
        </vmix>"""

        state = self.client._parse_state_xml(xml_text)

        assert isinstance(state, VMixState)
        assert state.recording is True
        assert state.recording_duration == 123
        assert state.streaming is False
        assert len(state.inputs) == 1
        assert state.inputs[0]["key"] == "abc"

    @pytest.mark.asyncio
    async def test_ping_success(self):
        """Test successful ping."""
        with patch.object(self.client, "get_state") as mock_get:
            mock_get.return_value = VMixState()

            result = await self.client.ping()

            assert result is True

    @pytest.mark.asyncio
    async def test_ping_failure(self):
        """Test failed ping."""
        with patch.object(self.client, "get_state") as mock_get:
            mock_get.return_value = None

            result = await self.client.ping()

            assert result is False


class TestReplayController:
    """Test cases for ReplayController."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=VMixClient)
        self.controller = ReplayController(self.mock_client)

    @pytest.mark.asyncio
    async def test_start_hand_recording(self):
        """Test starting hand recording."""
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=False))
        self.mock_client.start_recording = AsyncMock(return_value=True)

        result = await self.controller.start_hand_recording("table_1", 42)

        assert result is True
        assert self.controller.is_recording is True
        assert self.controller.current_hand_info == ("table_1", 42)
        self.mock_client.replay_mark_in.assert_called_once()

    @pytest.mark.asyncio
    async def test_end_hand_recording(self):
        """Test ending hand recording."""
        # First start a recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        await self.controller.start_hand_recording("table_1", 42)

        # Then end it
        self.mock_client.replay_mark_out = AsyncMock(return_value=True)
        self.mock_client.replay_export_last_event = AsyncMock(return_value=True)

        result = await self.controller.end_hand_recording()

        assert result is not None
        assert isinstance(result, HandRecordingResult)
        assert result.table_id == "table_1"
        assert result.hand_number == 42
        assert result.success is True
        assert self.controller.is_recording is False

    @pytest.mark.asyncio
    async def test_end_hand_recording_without_start(self):
        """Test ending recording without starting first."""
        result = await self.controller.end_hand_recording()

        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_hand_recording(self):
        """Test cancelling hand recording."""
        # Start a recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        await self.controller.start_hand_recording("table_1", 42)

        # Cancel it
        self.mock_client.replay_mark_cancel = AsyncMock(return_value=True)

        result = await self.controller.cancel_hand_recording()

        assert result is True
        assert self.controller.is_recording is False

    @pytest.mark.asyncio
    async def test_create_quick_replay(self):
        """Test creating quick replay."""
        self.mock_client.replay_mark_in_out_live = AsyncMock(return_value=True)

        result = await self.controller.create_quick_replay(30)

        assert result is True
        self.mock_client.replay_mark_in_out_live.assert_called_once_with(30)

    def test_get_current_duration(self):
        """Test getting current recording duration."""
        # Not recording
        assert self.controller.get_current_duration() is None

        # Simulate recording
        from datetime import datetime, timedelta

        self.controller._is_recording = True
        self.controller._mark_in_time = datetime.now() - timedelta(seconds=30)

        duration = self.controller.get_current_duration()
        assert duration is not None
        assert 29 <= duration <= 31  # Allow for timing variance
