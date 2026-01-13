"""GFX 파일 감시 핸들러."""

import asyncio
import logging
import threading
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

if TYPE_CHECKING:
    from src.sync_agent.config import SyncAgentSettings


@runtime_checkable
class SyncServiceProtocol(Protocol):
    """SyncService 인터페이스 프로토콜."""

    async def sync_file(self, file_path: str, operation: str = "created") -> Any:
        """파일 동기화."""
        ...

    async def process_offline_queue(self) -> int:
        """오프라인 큐 처리."""
        ...

logger = logging.getLogger(__name__)


class GFXFileHandler(FileSystemEventHandler):
    """PokerGFX JSON 파일 감시 핸들러.

    기능:
    - GFX 파일 패턴 매칭 (PGFX_live_data_export GameID=*.json)
    - 디바운스: 연속 이벤트 중 마지막만 처리
    - 비동기 동기화 예약
    """

    FILE_PATTERN = "PGFX_live_data_export GameID=*.json"

    def __init__(
        self,
        sync_service: SyncServiceProtocol,
        loop: asyncio.AbstractEventLoop,
        debounce_seconds: float = 2.0,
    ) -> None:
        """초기화.

        Args:
            sync_service: SyncService 또는 호환 인터페이스
            loop: asyncio 이벤트 루프
            debounce_seconds: 디바운스 지연 시간 (초)
        """
        super().__init__()
        self.sync_service: SyncServiceProtocol = sync_service
        self.loop = loop
        self.debounce_seconds = debounce_seconds
        self._pending: dict[str, asyncio.TimerHandle] = {}
        self._lock = threading.Lock()

    def _matches_pattern(self, path: str) -> bool:
        """파일명이 GFX 패턴과 일치하는지 확인.

        Args:
            path: 파일 경로

        Returns:
            True if matches pattern
        """
        filename = Path(path).name
        return fnmatch(filename, self.FILE_PATTERN)

    def on_created(self, event: FileSystemEvent) -> None:
        """파일 생성 이벤트.

        Args:
            event: watchdog 파일 이벤트
        """
        if event.is_directory:
            return
        if self._matches_pattern(str(event.src_path)):
            self._schedule_sync(str(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        """파일 수정 이벤트.

        Args:
            event: watchdog 파일 이벤트
        """
        if event.is_directory:
            return
        if self._matches_pattern(str(event.src_path)):
            self._schedule_sync(str(event.src_path), "modified")

    def _schedule_sync(self, path: str, operation: str) -> None:
        """디바운스 후 동기화 예약.

        연속 이벤트가 발생하면 이전 타이머를 취소하고
        마지막 이벤트만 처리합니다.

        Args:
            path: 파일 경로
            operation: 작업 타입 (created/modified)
        """
        with self._lock:
            # 기존 타이머 취소
            if path in self._pending:
                self._pending[path].cancel()

            # 새 타이머 예약
            def emit() -> None:
                asyncio.run_coroutine_threadsafe(
                    self.sync_service.sync_file(path, operation),
                    self.loop,
                )
                with self._lock:
                    self._pending.pop(path, None)

            handle = self.loop.call_later(self.debounce_seconds, emit)
            self._pending[path] = handle


class GFXFileWatcher:
    """GFX 파일 감시 워처.

    PollingObserver를 사용하여 NAS/SMB 파일 시스템을 감시합니다.
    """

    def __init__(
        self,
        settings: "SyncAgentSettings",
        sync_service: SyncServiceProtocol,
    ) -> None:
        """초기화.

        Args:
            settings: SyncAgent 설정
            sync_service: SyncService 또는 호환 인터페이스
        """
        self.settings = settings
        self.sync_service: SyncServiceProtocol = sync_service
        self._observer: PollingObserver | None = None
        self._running = False

    async def start(self) -> None:
        """감시 시작."""
        loop = asyncio.get_running_loop()
        handler = GFXFileHandler(
            self.sync_service,
            loop,
            debounce_seconds=self.settings.file_settle_delay,
        )

        self._observer = PollingObserver(timeout=2.0)
        self._observer.schedule(
            handler,
            self.settings.gfx_watch_path,
            recursive=False,
        )
        self._observer.start()
        self._running = True
        logger.info(f"Watching: {self.settings.gfx_watch_path}")

        # 기존 파일 스캔
        await self._scan_existing_files()

    async def _scan_existing_files(self) -> None:
        """시작 시 기존 파일 스캔 및 동기화."""
        watch_path = Path(self.settings.gfx_watch_path)
        pattern = "PGFX_live_data_export GameID=*.json"

        existing_files = list(watch_path.glob(pattern))
        if existing_files:
            logger.info(f"기존 파일 {len(existing_files)}개 발견, 동기화 시작...")
            for file_path in existing_files:
                try:
                    await self.sync_service.sync_file(str(file_path), "existing")
                except Exception as e:
                    logger.error(f"기존 파일 동기화 실패: {file_path.name} - {e}")

    async def stop(self) -> None:
        """감시 중지."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
        self._running = False
        logger.info("GFX file watcher stopped")

    async def run_forever(self) -> None:
        """무한 루프 (메인용).

        파일 감시 + 주기적 오프라인 큐 처리.
        """
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(self.settings.queue_process_interval)
                await self.sync_service.process_offline_queue()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
