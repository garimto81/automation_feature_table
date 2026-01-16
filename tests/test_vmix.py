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

    @pytest.mark.asyncio
    async def test_call_api_timeout_exception(self):
        """Test API call with timeout exception."""
        with patch.object(self.client, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Timeout")
            mock_ensure.return_value = mock_client

            result = await self.client._call_api("StartRecording")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_state_exception(self):
        """Test get_state with exception."""
        with patch.object(self.client, "_ensure_client") as mock_ensure:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Network error")
            mock_ensure.return_value = mock_client

            result = await self.client.get_state()

            assert result is None

    @pytest.mark.asyncio
    async def test_is_recording_true(self):
        """Test is_recording when recording is active."""
        with patch.object(self.client, "get_state") as mock_get:
            mock_get.return_value = VMixState(recording=True)

            result = await self.client.is_recording()

            assert result is True

    @pytest.mark.asyncio
    async def test_is_recording_false(self):
        """Test is_recording when not recording."""
        with patch.object(self.client, "get_state") as mock_get:
            mock_get.return_value = VMixState(recording=False)

            result = await self.client.is_recording()

            assert result is False

    @pytest.mark.asyncio
    async def test_is_recording_state_none(self):
        """Test is_recording when state is None."""
        with patch.object(self.client, "get_state") as mock_get:
            mock_get.return_value = None

            result = await self.client.is_recording()

            assert result is False

    @pytest.mark.asyncio
    async def test_toggle_recording(self):
        """Test toggle recording API call."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.toggle_recording()

            assert result is True
            mock_call.assert_called_once_with("StartStopRecording")

    @pytest.mark.asyncio
    async def test_replay_start_recording_with_channel(self):
        """Test replay start recording with channel."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_start_recording(channel="A")

            assert result is True
            mock_call.assert_called_once_with("ReplayStartRecording", Channel="A")

    @pytest.mark.asyncio
    async def test_replay_start_recording_without_channel(self):
        """Test replay start recording without channel."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_start_recording()

            assert result is True
            mock_call.assert_called_once_with("ReplayStartRecording")

    @pytest.mark.asyncio
    async def test_replay_stop_recording_with_channel(self):
        """Test replay stop recording with channel."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_stop_recording(channel="B")

            assert result is True
            mock_call.assert_called_once_with("ReplayStopRecording", Channel="B")

    @pytest.mark.asyncio
    async def test_replay_stop_recording_without_channel(self):
        """Test replay stop recording without channel."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_stop_recording()

            assert result is True
            mock_call.assert_called_once_with("ReplayStopRecording")

    @pytest.mark.asyncio
    async def test_replay_mark_in_out(self):
        """Test replay mark in/out with duration."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_mark_in_out(30)

            assert result is True
            mock_call.assert_called_once_with("ReplayMarkInOut", Value="30")

    @pytest.mark.asyncio
    async def test_replay_mark_in_out_with_channel(self):
        """Test replay mark in/out with duration and channel."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_mark_in_out(30, channel="A")

            assert result is True
            mock_call.assert_called_once_with("ReplayMarkInOut", Value="30", Channel="A")

    @pytest.mark.asyncio
    async def test_replay_mark_cancel(self):
        """Test replay mark cancel."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_mark_cancel()

            assert result is True
            mock_call.assert_called_once_with("ReplayMarkCancel")

    @pytest.mark.asyncio
    async def test_replay_play_event(self):
        """Test replay play event."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_play_event(5)

            assert result is True
            mock_call.assert_called_once_with("ReplayPlayEvent", Value="5")

    @pytest.mark.asyncio
    async def test_replay_play_event_default(self):
        """Test replay play event with default (last event)."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_play_event(0)

            assert result is True
            mock_call.assert_called_once_with("ReplayPlayEvent")

    @pytest.mark.asyncio
    async def test_replay_play_last_event(self):
        """Test replay play last event."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_play_last_event()

            assert result is True
            mock_call.assert_called_once_with("ReplayPlayLastEvent")

    @pytest.mark.asyncio
    async def test_replay_stop(self):
        """Test replay stop."""
        with patch.object(self.client, "_call_api") as mock_call:
            mock_call.return_value = True

            result = await self.client.replay_stop()

            assert result is True
            mock_call.assert_called_once_with("ReplayStopEvents")

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test closing client connection."""
        self.client._client = AsyncMock()

        await self.client.close()

        assert self.client._client is None

    @pytest.mark.asyncio
    async def test_close_client_when_none(self):
        """Test closing when client is already None."""
        self.client._client = None

        await self.client.close()

        assert self.client._client is None


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


class TestSMPTETimecode:
    """Test cases for SMPTE timecode handling."""

    def test_timecode_str_format_normal(self):
        """Test timecode string formatting (normal)."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode(hours=1, minutes=23, seconds=45, frames=12)
        assert str(tc) == "01:23:45:12"

    def test_timecode_str_format_drop_frame(self):
        """Test timecode string formatting (drop-frame)."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode(hours=1, minutes=23, seconds=45, frames=12, drop_frame=True)
        assert str(tc) == "01:23:45;12"

    def test_timecode_to_total_frames(self):
        """Test conversion to total frames."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode(hours=0, minutes=1, seconds=0, frames=0, frame_rate=30.0)
        assert tc.to_total_frames() == 1800  # 60 seconds * 30 fps

    def test_timecode_to_seconds(self):
        """Test conversion to seconds."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode(hours=0, minutes=1, seconds=30, frames=15, frame_rate=30.0)
        assert tc.to_seconds() == 90.5  # 90 + 15/30

    def test_timecode_from_string_valid(self):
        """Test parsing valid timecode string."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("01:23:45:12")
        assert tc is not None
        assert tc.hours == 1
        assert tc.minutes == 23
        assert tc.seconds == 45
        assert tc.frames == 12
        assert tc.drop_frame is False

    def test_timecode_from_string_drop_frame(self):
        """Test parsing drop-frame timecode."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("01:23:45;12")
        assert tc is not None
        assert tc.drop_frame is True

    def test_timecode_from_string_invalid_format(self):
        """Test parsing invalid timecode format."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("invalid")
        assert tc is None

    def test_timecode_from_string_invalid_hours(self):
        """Test parsing timecode with invalid hours."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("25:00:00:00")
        assert tc is None

    def test_timecode_from_string_invalid_minutes(self):
        """Test parsing timecode with invalid minutes."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("01:61:00:00")
        assert tc is None

    def test_timecode_from_string_invalid_seconds(self):
        """Test parsing timecode with invalid seconds."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("01:00:61:00")
        assert tc is None

    def test_timecode_from_string_invalid_frames(self):
        """Test parsing timecode with invalid frames."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_string("01:00:00:30", frame_rate=30.0)
        assert tc is None

    def test_timecode_from_seconds(self):
        """Test creating timecode from seconds."""
        from src.vmix.replay_controller import SMPTETimecode

        tc = SMPTETimecode.from_seconds(3661.5, frame_rate=30.0)
        assert tc.hours == 1
        assert tc.minutes == 1
        assert tc.seconds == 1

    def test_timecode_subtraction(self):
        """Test timecode subtraction."""
        from src.vmix.replay_controller import SMPTETimecode

        tc1 = SMPTETimecode(hours=1, minutes=0, seconds=30, frames=0, frame_rate=30.0)
        tc2 = SMPTETimecode(hours=1, minutes=0, seconds=0, frames=0, frame_rate=30.0)
        diff = tc1 - tc2
        assert diff.seconds == 30


class TestHandRecordingResult:
    """Test cases for HandRecordingResult."""

    def test_has_timecode_true(self):
        """Test has_timecode property when both timecodes present."""
        from datetime import datetime

        from src.vmix.replay_controller import HandRecordingResult, SMPTETimecode

        result = HandRecordingResult(
            table_id="table_1",
            hand_number=42,
            mark_in_time=datetime.now(),
            mark_out_time=datetime.now(),
            duration_seconds=120,
            success=True,
            mark_in_timecode=SMPTETimecode(hours=1, minutes=0, seconds=0, frames=0),
            mark_out_timecode=SMPTETimecode(hours=1, minutes=2, seconds=0, frames=0),
        )
        assert result.has_timecode is True

    def test_has_timecode_false(self):
        """Test has_timecode property when timecodes missing."""
        from datetime import datetime

        from src.vmix.replay_controller import HandRecordingResult

        result = HandRecordingResult(
            table_id="table_1",
            hand_number=42,
            mark_in_time=datetime.now(),
            mark_out_time=datetime.now(),
            duration_seconds=120,
            success=True,
        )
        assert result.has_timecode is False

    def test_to_edl_entry(self):
        """Test EDL entry generation."""
        from datetime import datetime

        from src.vmix.replay_controller import HandRecordingResult, SMPTETimecode

        result = HandRecordingResult(
            table_id="table_1",
            hand_number=42,
            mark_in_time=datetime.now(),
            mark_out_time=datetime.now(),
            duration_seconds=120,
            success=True,
            mark_in_timecode=SMPTETimecode(hours=1, minutes=0, seconds=0, frames=0),
            mark_out_timecode=SMPTETimecode(hours=1, minutes=2, seconds=0, frames=0),
        )
        edl = result.to_edl_entry(1, "001")
        assert "001" in edl
        assert "01:00:00:00" in edl
        assert "01:02:00:00" in edl
        assert "table_1" in edl
        assert "42" in edl

    def test_to_edl_entry_no_timecode(self):
        """Test EDL entry generation without timecode."""
        from datetime import datetime

        from src.vmix.replay_controller import HandRecordingResult

        result = HandRecordingResult(
            table_id="table_1",
            hand_number=42,
            mark_in_time=datetime.now(),
            mark_out_time=datetime.now(),
            duration_seconds=120,
            success=True,
        )
        edl = result.to_edl_entry(1, "001")
        assert edl == ""


class TestReplayControllerTimecode:
    """Test cases for ReplayController timecode support."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MagicMock(spec=VMixClient)
        self.controller = ReplayController(
            self.mock_client, track_timecode=True, frame_rate=30.0
        )

    @pytest.mark.asyncio
    async def test_get_current_timecode_success(self):
        """Test getting current timecode."""
        from src.vmix.replay_controller import SMPTETimecode

        mock_state = MagicMock()
        mock_state.timecode = "01:23:45:12"
        self.mock_client.get_state = AsyncMock(return_value=mock_state)

        tc = await self.controller.get_current_timecode()

        assert tc is not None
        assert isinstance(tc, SMPTETimecode)

    @pytest.mark.asyncio
    async def test_get_current_timecode_no_timecode_attr(self):
        """Test getting timecode when state has no timecode attribute."""
        mock_state = VMixState()
        self.mock_client.get_state = AsyncMock(return_value=mock_state)

        tc = await self.controller.get_current_timecode()

        assert tc is None

    @pytest.mark.asyncio
    async def test_get_current_timecode_exception(self):
        """Test getting timecode with exception."""
        self.mock_client.get_state = AsyncMock(side_effect=Exception("Error"))

        tc = await self.controller.get_current_timecode()

        assert tc is None

    @pytest.mark.asyncio
    async def test_start_hand_recording_with_existing_recording(self):
        """Test starting new hand when already recording."""
        # Start first recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        await self.controller.start_hand_recording("table_1", 1)

        # Start second recording (should cancel first)
        self.mock_client.replay_mark_cancel = AsyncMock(return_value=True)
        result = await self.controller.start_hand_recording("table_2", 2)

        assert result is True
        self.mock_client.replay_mark_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_end_hand_recording_with_export_false(self):
        """Test ending recording without exporting."""
        # Start recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        await self.controller.start_hand_recording("table_1", 42)

        # End without export
        self.mock_client.replay_mark_out = AsyncMock(return_value=True)
        self.mock_client.replay_export_last_event = AsyncMock()

        result = await self.controller.end_hand_recording(export_event=False)

        assert result is not None
        self.mock_client.replay_export_last_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_end_hand_recording_export_failure(self):
        """Test ending recording with export failure."""
        # Start recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        await self.controller.start_hand_recording("table_1", 42)

        # End with export failure
        self.mock_client.replay_mark_out = AsyncMock(return_value=True)
        self.mock_client.replay_export_last_event = AsyncMock(return_value=False)

        result = await self.controller.end_hand_recording(export_event=True)

        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_end_hand_recording_mark_out_failure(self):
        """Test ending recording with mark-out failure."""
        # Start recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        await self.controller.start_hand_recording("table_1", 42)

        # Mark-out fails
        self.mock_client.replay_mark_out = AsyncMock(return_value=False)

        result = await self.controller.end_hand_recording()

        assert result is not None
        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_end_hand_recording_calls_callback(self):
        """Test that end_hand_recording calls completion callback."""
        callback_called = False
        callback_result = None

        def callback(result):
            nonlocal callback_called, callback_result
            callback_called = True
            callback_result = result

        controller = ReplayController(self.mock_client, on_recording_complete=callback)

        # Start and end recording
        self.mock_client.replay_mark_in = AsyncMock(return_value=True)
        self.mock_client.get_state = AsyncMock(return_value=VMixState(recording=True))
        self.mock_client.replay_mark_out = AsyncMock(return_value=True)
        self.mock_client.replay_export_last_event = AsyncMock(return_value=True)

        await controller.start_hand_recording("table_1", 42)
        result = await controller.end_hand_recording()

        assert callback_called is True
        assert callback_result is not None
        assert callback_result.table_id == "table_1"

    @pytest.mark.asyncio
    async def test_start_hand_recording_failed_mark_in(self):
        """Test starting recording with failed mark-in."""
        self.mock_client.replay_mark_in = AsyncMock(return_value=False)

        result = await self.controller.start_hand_recording("table_1", 42)

        assert result is False
        assert self.controller.is_recording is False
