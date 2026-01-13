"""Streamlit GUI for GFX Sync Agent.

GFX PC에서 Supabase로 JSON 파일을 동기화하는 에이전트의 GUI입니다.
실시간 상태, 로그, 전송 통계를 눈으로 확인할 수 있습니다.

Usage:
    streamlit run src/sync_agent/gui/app.py
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[3]))


class SyncStatus(Enum):
    """Sync agent status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class LogEntry:
    """Log entry for display."""
    timestamp: datetime
    level: str
    message: str

    def __str__(self) -> str:
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.level}: {self.message}"


@dataclass
class SyncStats:
    """Sync statistics."""
    files_synced: int = 0
    files_failed: int = 0
    files_queued: int = 0
    bytes_transferred: int = 0
    last_sync_time: datetime | None = None

    @property
    def bytes_transferred_str(self) -> str:
        """Format bytes as human readable."""
        if self.bytes_transferred < 1024:
            return f"{self.bytes_transferred} B"
        elif self.bytes_transferred < 1024 * 1024:
            return f"{self.bytes_transferred / 1024:.1f} KB"
        else:
            return f"{self.bytes_transferred / (1024 * 1024):.1f} MB"


class SyncAgentGUI:
    """GUI wrapper for Sync Agent."""

    def __init__(self) -> None:
        self.status = SyncStatus.STOPPED
        self.supabase_connected = False
        self.logs: deque[LogEntry] = deque(maxlen=100)
        self.stats = SyncStats()
        self._agent: Any = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Settings
        self.watch_path = "C:/GFX/output"
        self.supabase_url = ""
        self.supabase_key = ""

    def add_log(self, level: str, message: str) -> None:
        """Add a log entry."""
        self.logs.append(LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
        ))

    def get_logs(self, limit: int = 50) -> list[LogEntry]:
        """Get recent logs."""
        return list(self.logs)[-limit:]

    def _run_agent(self) -> None:
        """Run agent in background thread."""
        self.add_log("INFO", "[1/8] 스레드 시작됨")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.add_log("INFO", "[2/8] 이벤트 루프 생성")

        try:
            # status는 start()에서 이미 STARTING으로 설정됨
            self.add_log("INFO", "[3/8] Supabase 연결 시도...")

            # Check Supabase (sync)
            try:
                from supabase import create_client
                self.add_log("INFO", "[3a] supabase 모듈 임포트 완료")

                _ = create_client(self.supabase_url, self.supabase_key)
                self.add_log("SUCCESS", "[3b] Supabase 클라이언트 생성 완료")
                self.supabase_connected = True
            except Exception as e:
                self.add_log("ERROR", f"[3c] Supabase 연결 실패: {e}")
                self.supabase_connected = False
                self.status = SyncStatus.ERROR
                return

            self.add_log("INFO", "[4/8] 환경변수 설정 중...")

            # Create settings
            import os
            os.environ["SUPABASE_URL"] = self.supabase_url
            os.environ["SUPABASE_KEY"] = self.supabase_key
            os.environ["GFX_WATCH_PATH"] = self.watch_path

            self.add_log("INFO", "[5/8] 모듈 임포트 중...")

            # Import and run agent
            from src.sync_agent.config import SyncAgentSettings
            from src.sync_agent.file_handler import GFXFileWatcher
            from src.sync_agent.local_queue import LocalQueue
            self.add_log("INFO", "[5a] 모듈 임포트 완료")

            self.add_log("INFO", "[6/8] 설정 로드 중...")
            settings = SyncAgentSettings()  # type: ignore[call-arg]
            self.add_log("INFO", f"[6a] 감시 경로: {settings.gfx_watch_path}")
            self.add_log("INFO", f"[6b] 큐 DB: {settings.queue_db_path}")

            self.add_log("INFO", "[7/8] 컴포넌트 초기화 중...")

            # Initialize components
            queue = LocalQueue(
                db_path=settings.queue_db_path,
                max_retries=settings.max_retries,
            )
            self.add_log("INFO", "[7a] 로컬 큐 생성 완료")

            sync_service = SyncServiceWrapper(
                settings=settings,
                local_queue=queue,
                gui=self,
            )
            self.add_log("INFO", "[7b] 동기화 서비스 생성 완료")

            watcher = GFXFileWatcher(
                settings=settings,
                sync_service=sync_service,
            )
            self.add_log("INFO", "[7c] 파일 감시자 생성 완료")

            self.status = SyncStatus.RUNNING
            self.add_log("SUCCESS", "[8/8] 감시 시작!")

            # Run watcher
            async def run_with_stop() -> None:
                watcher_task = asyncio.create_task(watcher.run_forever())

                while not self._stop_event.is_set():
                    await asyncio.sleep(0.5)

                await watcher.stop()
                watcher_task.cancel()

            loop.run_until_complete(run_with_stop())

        except Exception as e:
            self.add_log("ERROR", f"에러 발생: {e}")
            self.status = SyncStatus.ERROR
        finally:
            self.status = SyncStatus.STOPPED
            self.add_log("INFO", "Sync Agent 종료됨")
            loop.close()

    def start(self) -> None:
        """Start the sync agent."""
        if self._thread and self._thread.is_alive():
            return

        # 즉시 상태 변경 (UI 반영을 위해 스레드 시작 전에 설정)
        self.status = SyncStatus.STARTING
        self.add_log("INFO", "에이전트 시작 요청됨")

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_agent, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the sync agent."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.status = SyncStatus.STOPPED


class SyncServiceWrapper:
    """Wrapper for SyncService to capture events for GUI."""

    def __init__(
        self,
        settings: Any,
        local_queue: Any,
        gui: SyncAgentGUI,
    ) -> None:
        from src.sync_agent.sync_service import SyncService
        self._service = SyncService(settings=settings, local_queue=local_queue)
        self._gui = gui

    async def sync_file(self, file_path: str, operation: str = "created") -> Any:
        """Sync file and update GUI."""
        path = Path(file_path)
        self._gui.add_log("INFO", f"동기화 중: {path.name} ({operation})")

        try:
            result = await self._service.sync_file(file_path, operation)

            if result.success:
                self._gui.stats.files_synced += 1
                self._gui.stats.last_sync_time = datetime.now()
                # Estimate size from file
                try:
                    size = path.stat().st_size
                    self._gui.stats.bytes_transferred += size
                except Exception:
                    pass
                self._gui.add_log(
                    "SUCCESS", f"동기화 완료: {path.name} (핸드 {result.hand_count}개)"
                )
            else:
                self._gui.stats.files_failed += 1
                if result.queued:
                    self._gui.add_log("WARNING", f"동기화 실패 (큐에 추가): {path.name}")
                else:
                    self._gui.add_log("ERROR", f"동기화 실패: {path.name}")

            return result
        except Exception as e:
            self._gui.stats.files_failed += 1
            self._gui.add_log("ERROR", f"동기화 에러: {path.name} - {e}")
            from src.sync_agent.sync_service import SyncResult
            return SyncResult(success=False, session_id=None, hand_count=0, error_message=str(e))

    async def health_check(self) -> bool:
        """Health check."""
        return await self._service.health_check()

    async def process_offline_queue(self) -> int:
        """Process offline queue."""
        return await self._service.process_offline_queue()


def load_env_settings() -> tuple[str, str]:
    """Load Supabase settings from .env file."""
    env_path = Path(__file__).parents[3] / ".env"

    supabase_url = ""
    supabase_key = ""

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SUPABASE_URL="):
                    supabase_url = line.split("=", 1)[1].strip()
                elif line.startswith("SUPABASE_KEY="):
                    supabase_key = line.split("=", 1)[1].strip()

    return supabase_url, supabase_key


def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(
        page_title="GFX Sync Agent",
        page_icon="🔄",
        layout="wide",
    )

    st.title("🔄 GFX Sync Agent")
    st.markdown("GFX PC → Supabase 실시간 동기화")

    # Initialize session state
    if "gui" not in st.session_state:
        st.session_state.gui = SyncAgentGUI()
        # Load settings from .env
        url, key = load_env_settings()
        st.session_state.gui.supabase_url = url
        st.session_state.gui.supabase_key = key

    gui: SyncAgentGUI = st.session_state.gui

    # Sidebar: Settings
    with st.sidebar:
        # === Control Buttons at TOP ===
        st.header("🎮 제어")

        col1, col2 = st.columns(2)

        with col1:
            is_running = gui.status in (SyncStatus.RUNNING, SyncStatus.STARTING)
            btn_text = "⏳ 실행중..." if is_running else "▶️ 시작"
            if st.button(
                btn_text,
                disabled=is_running,
                use_container_width=True,
                type="primary" if not is_running else "secondary",
            ):
                if not gui.supabase_url or not gui.supabase_key:
                    st.error("Supabase 설정을 입력하세요")
                elif not Path(gui.watch_path).exists():
                    st.error("감시 경로가 존재하지 않습니다")
                else:
                    gui.start()
                    time.sleep(0.3)  # 스레드 시작 대기
                    st.rerun()

        with col2:
            is_stopped = gui.status not in (SyncStatus.RUNNING, SyncStatus.STARTING)
            if st.button(
                "⏹️ 정지",
                disabled=is_stopped,
                use_container_width=True,
            ):
                gui.stop()
                st.rerun()

        # Status indicator
        status_map = {
            SyncStatus.STOPPED: ("🔴", "정지됨"),
            SyncStatus.STARTING: ("🟡", "시작 중..."),
            SyncStatus.RUNNING: ("🟢", "실행 중"),
            SyncStatus.ERROR: ("❌", "오류"),
        }
        icon, text = status_map.get(gui.status, ("⚪", "알 수 없음"))
        st.markdown(f"**{icon} {text}**")

        st.divider()

        # === Settings (collapsible) ===
        with st.expander("⚙️ 설정", expanded=False):
            # Supabase Settings
            st.caption("🔗 Supabase")

            supabase_url = st.text_input(
                "URL",
                value=gui.supabase_url,
                type="default",
                label_visibility="collapsed",
                placeholder="https://xxx.supabase.co",
            )
            gui.supabase_url = supabase_url

            supabase_key = st.text_input(
                "Key",
                value=gui.supabase_key,
                type="password",
                label_visibility="collapsed",
                placeholder="Supabase Key",
            )
            gui.supabase_key = supabase_key

            st.caption("📂 감시 경로")

            watch_path = st.text_input(
                "Path",
                value=gui.watch_path,
                label_visibility="collapsed",
            )
            gui.watch_path = watch_path

        # Path status (always visible)
        watch_path_obj = Path(gui.watch_path)
        if watch_path_obj.exists():
            json_files = list(watch_path_obj.glob("*.json"))
            st.caption(f"📂 {gui.watch_path}")
            st.caption(f"📄 JSON 파일: {len(json_files)}개")
        else:
            st.error(f"❌ 경로 없음: {gui.watch_path}")
            if st.button("📁 폴더 생성"):
                try:
                    watch_path_obj.mkdir(parents=True, exist_ok=True)
                    st.success("폴더 생성 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"생성 실패: {e}")

    # === Main Content ===

    # Status Section
    status_colors = {
        SyncStatus.STOPPED: ("🔴", "정지됨"),
        SyncStatus.STARTING: ("🟡", "시작 중..."),
        SyncStatus.RUNNING: ("🟢", "실행 중"),
        SyncStatus.ERROR: ("❌", "오류 발생"),
    }
    icon, text = status_colors.get(gui.status, ("⚪", "알 수 없음"))

    st.header(f"{icon} 상태: {text}")

    # Stats Section
    st.subheader("📊 동기화 통계")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "✅ 성공",
            f"{gui.stats.files_synced}개",
            help="성공적으로 동기화된 파일 수",
        )

    with col2:
        st.metric(
            "❌ 실패",
            f"{gui.stats.files_failed}개",
            help="동기화 실패한 파일 수",
        )

    with col3:
        st.metric(
            "📦 전송량",
            gui.stats.bytes_transferred_str,
            help="총 전송된 데이터량",
        )

    with col4:
        last_sync = (
            gui.stats.last_sync_time.strftime("%H:%M:%S")
            if gui.stats.last_sync_time
            else "-"
        )
        st.metric(
            "🕐 마지막 동기화",
            last_sync,
            help="마지막 성공한 동기화 시간",
        )

    st.divider()

    # Logs Section
    st.subheader("📝 실시간 로그")

    logs = gui.get_logs(limit=50)

    if logs:
        log_container = st.container(height=400)
        with log_container:
            for log in reversed(logs):
                if log.level == "ERROR":
                    st.error(str(log))
                elif log.level == "WARNING":
                    st.warning(str(log))
                elif log.level == "SUCCESS":
                    st.success(str(log))
                else:
                    st.text(str(log))
    else:
        st.info("로그가 없습니다. 시작 버튼을 눌러 동기화를 시작하세요.")

    # Auto-refresh while running
    if gui.status in (SyncStatus.RUNNING, SyncStatus.STARTING):
        time.sleep(1)
        st.rerun()


if __name__ == "__main__":
    main()
