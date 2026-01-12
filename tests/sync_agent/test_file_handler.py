"""GFXFileHandler 테스트."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileModifiedEvent

from src.sync_agent.file_handler import GFXFileHandler, GFXFileWatcher
from src.sync_agent.sync_service import SyncResult


@pytest.fixture
def mock_sync_service() -> MagicMock:
    """Mock SyncService."""
    service = MagicMock()
    service.sync_file = AsyncMock(
        return_value=SyncResult(success=True, session_id="123", hand_count=10)
    )
    return service


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    """이벤트 루프 fixture."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def file_handler(
    mock_sync_service: MagicMock,
    event_loop: asyncio.AbstractEventLoop,
) -> GFXFileHandler:
    """GFXFileHandler fixture."""
    return GFXFileHandler(
        sync_service=mock_sync_service,
        loop=event_loop,
        debounce_seconds=0.1,  # 테스트용 짧은 debounce
    )


class TestGFXFileHandler:
    """GFXFileHandler 테스트."""

    def test_matches_pattern_valid(self, file_handler: GFXFileHandler) -> None:
        """유효한 GFX 파일명 매칭."""
        valid_filenames = [
            "PGFX_live_data_export GameID=123.json",
            "PGFX_live_data_export GameID=456_test.json",
            "PGFX_live_data_export GameID=789-foo.json",
        ]

        for filename in valid_filenames:
            assert file_handler._matches_pattern(filename), f"Failed: {filename}"

    def test_matches_pattern_invalid(self, file_handler: GFXFileHandler) -> None:
        """무효한 파일명."""
        invalid_filenames = [
            "config.json",
            "readme.txt",
            "session_123.json",
            "PGFX_data.json",  # 패턴 불일치
            "backup_GameID=123.json",  # prefix 불일치
        ]

        for filename in invalid_filenames:
            assert not file_handler._matches_pattern(
                filename
            ), f"Should not match: {filename}"

    def test_on_created_triggers_sync(
        self,
        file_handler: GFXFileHandler,
        mock_sync_service: MagicMock,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """파일 생성 시 동기화 예약."""
        event = FileCreatedEvent("C:/GFX/output/PGFX_live_data_export GameID=123.json")

        file_handler.on_created(event)

        # 디바운스 대기
        event_loop.run_until_complete(asyncio.sleep(0.2))

        # sync_file이 호출되었는지 확인
        mock_sync_service.sync_file.assert_called_once()
        args, _ = mock_sync_service.sync_file.call_args
        assert args[0] == event.src_path
        assert args[1] == "created"

    def test_on_modified_triggers_sync(
        self,
        file_handler: GFXFileHandler,
        mock_sync_service: MagicMock,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """파일 수정 시 동기화 예약."""
        event = FileModifiedEvent("C:/GFX/output/PGFX_live_data_export GameID=456.json")

        file_handler.on_modified(event)

        # 디바운스 대기
        event_loop.run_until_complete(asyncio.sleep(0.2))

        mock_sync_service.sync_file.assert_called_once()
        args, _ = mock_sync_service.sync_file.call_args
        assert args[0] == event.src_path
        assert args[1] == "modified"

    def test_ignores_directories(
        self,
        file_handler: GFXFileHandler,
        mock_sync_service: MagicMock,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """디렉토리 이벤트 무시."""
        event = DirCreatedEvent("C:/GFX/output/subdir")

        file_handler.on_created(event)

        # 디바운스 대기
        event_loop.run_until_complete(asyncio.sleep(0.2))

        mock_sync_service.sync_file.assert_not_called()

    def test_ignores_non_matching_files(
        self,
        file_handler: GFXFileHandler,
        mock_sync_service: MagicMock,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """패턴 불일치 파일 무시."""
        event = FileCreatedEvent("C:/GFX/output/config.json")

        file_handler.on_created(event)

        # 디바운스 대기
        event_loop.run_until_complete(asyncio.sleep(0.2))

        mock_sync_service.sync_file.assert_not_called()

    async def test_debounce_rapid_events(
        self,
        mock_sync_service: MagicMock,
    ) -> None:
        """빠른 연속 이벤트 디바운스 (마지막만 실행)."""
        # 테스트용 이벤트 루프 생성
        loop = asyncio.get_running_loop()
        handler = GFXFileHandler(
            sync_service=mock_sync_service,
            loop=loop,
            debounce_seconds=0.1,
        )

        filepath = "C:/GFX/output/PGFX_live_data_export GameID=123.json"

        # 빠른 연속 이벤트 (created → modified → modified)
        event1 = FileCreatedEvent(filepath)
        event2 = FileModifiedEvent(filepath)
        event3 = FileModifiedEvent(filepath)

        handler.on_created(event1)
        await asyncio.sleep(0.05)

        handler.on_modified(event2)
        await asyncio.sleep(0.05)

        handler.on_modified(event3)

        # 디바운스 대기 (마지막 이벤트 기준)
        await asyncio.sleep(0.2)

        # 마지막 이벤트만 실행됨
        assert mock_sync_service.sync_file.call_count == 1
        args, _ = mock_sync_service.sync_file.call_args
        assert args[0] == filepath
        assert args[1] == "modified"  # 마지막 event_type


class TestGFXFileWatcher:
    """GFXFileWatcher 테스트."""

    async def test_start_and_stop(
        self,
        mock_sync_settings,
        mock_sync_service: MagicMock,
        tmp_path: Path,
    ) -> None:
        """시작/중지 테스트."""
        # GFX 감시 경로 생성
        watch_path = tmp_path / "gfx_output"
        watch_path.mkdir()
        mock_sync_settings.gfx_watch_path = str(watch_path)

        watcher = GFXFileWatcher(
            settings=mock_sync_settings,
            sync_service=mock_sync_service,
        )

        # 시작
        await watcher.start()
        assert watcher._running is True
        assert watcher._observer is not None

        # 중지
        await watcher.stop()
        assert watcher._running is False

    async def test_process_existing_files_on_start(
        self,
        mock_sync_settings,
        mock_sync_service: MagicMock,
        tmp_path: Path,
    ) -> None:
        """시작 시 기존 파일 처리 (선택)."""
        # 감시 경로 생성
        watch_path = tmp_path / "gfx_output"
        watch_path.mkdir()
        mock_sync_settings.gfx_watch_path = str(watch_path)

        # 기존 파일 생성
        existing_file = watch_path / "PGFX_live_data_export GameID=123.json"
        existing_file.write_text('{"ID": "123", "Hands": []}')

        watcher = GFXFileWatcher(
            settings=mock_sync_settings,
            sync_service=mock_sync_service,
        )

        # 시작 시 기존 파일 처리 확인은 run_forever에서 수행됨
        # 여기서는 시작만 확인
        await watcher.start()
        assert watcher._running is True

        await watcher.stop()

    async def test_run_forever_calls_process_queue(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run_forever가 주기적으로 오프라인 큐 처리."""
        # 로컬 설정 생성
        from src.sync_agent.config import SyncAgentSettings

        watch_path = tmp_path / "gfx_output"
        watch_path.mkdir()

        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test_key")
        monkeypatch.setenv("GFX_WATCH_PATH", str(watch_path))
        monkeypatch.setenv("QUEUE_DB_PATH", str(tmp_path / "test_queue.db"))

        settings = SyncAgentSettings(_env_file=None)
        settings.queue_process_interval = 1  # 1초마다

        # Mock SyncService
        mock_service = MagicMock()
        mock_service.sync_file = AsyncMock()
        mock_service.process_offline_queue = AsyncMock(return_value=0)

        watcher = GFXFileWatcher(
            settings=settings,
            sync_service=mock_service,
        )

        # run_forever를 짧게 실행 후 취소
        async def run_and_cancel() -> None:
            task = asyncio.create_task(watcher.run_forever())
            await asyncio.sleep(1.5)  # 1.5초 대기 (1회 실행 보장)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()

        # process_offline_queue가 최소 1회 호출되었는지 확인
        assert mock_service.process_offline_queue.call_count >= 1
