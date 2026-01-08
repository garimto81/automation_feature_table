"""Streamlit GUI for GFX JSON Simulator."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[3]))

from src.simulator.config import get_simulator_settings
from src.simulator.gfx_json_simulator import GFXJsonSimulator, Status
from src.simulator.gui.file_browser import (
    format_file_display,
    is_tkinter_available,
    scan_json_files,
    select_folder,
)


def format_duration(seconds: float) -> str:
    """Format seconds as human readable duration."""
    if seconds <= 0:
        return "0s"
    td = timedelta(seconds=int(seconds))
    parts = []
    if td.days > 0:
        parts.append(f"{td.days}d")
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def run_simulation_thread(simulator: GFXJsonSimulator) -> None:
    """Run simulation in background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(simulator.run())
    finally:
        loop.close()


def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(
        page_title="GFX JSON Simulator",
        page_icon="🎴",
        layout="wide",
    )

    st.title("🎴 GFX JSON Simulator")
    st.markdown("NAS 테스트를 위한 JSON 파일 시뮬레이터")

    # Initialize session state
    if "simulator" not in st.session_state:
        st.session_state.simulator = None
    if "thread" not in st.session_state:
        st.session_state.thread = None
    if "source_path" not in st.session_state:
        st.session_state.source_path = ""
    if "target_path" not in st.session_state:
        st.session_state.target_path = ""
    if "scanned_files" not in st.session_state:
        st.session_state.scanned_files = []
    if "selected_files" not in st.session_state:
        st.session_state.selected_files = []

    settings = get_simulator_settings()

    # Sidebar: Settings
    with st.sidebar:
        st.header("⚙️ 설정")

        # === Source Path Section ===
        st.subheader("📂 소스 경로")

        source_col1, source_col2 = st.columns([3, 1])
        with source_col1:
            source_input = st.text_input(
                "Source Path",
                value=st.session_state.source_path or str(settings.source_path),
                help="GFX JSON 파일이 있는 소스 디렉토리",
                label_visibility="collapsed",
            )
        with source_col2:
            if is_tkinter_available():
                if st.button("📁", help="폴더 선택", key="browse_source"):
                    folder = select_folder(
                        title="소스 폴더 선택",
                        initial_dir=source_input or str(Path.cwd()),
                    )
                    if folder:
                        st.session_state.source_path = folder
                        st.session_state.scanned_files = []
                        st.rerun()

        # Update session state
        if source_input != st.session_state.source_path:
            st.session_state.source_path = source_input
            st.session_state.scanned_files = []

        # Scan button
        if st.button("🔍 파일 스캔", use_container_width=True):
            source_path = Path(st.session_state.source_path)
            if source_path.exists():
                with st.spinner("파일 스캔 중..."):
                    st.session_state.scanned_files = scan_json_files(source_path)
                    st.session_state.selected_files = []
                st.success(f"{len(st.session_state.scanned_files)}개 파일 발견")
            else:
                st.error(f"경로를 찾을 수 없음: {source_path}")

        # === Target Path Section ===
        st.subheader("📁 출력 경로 (NAS)")

        target_col1, target_col2 = st.columns([3, 1])
        with target_col1:
            target_input = st.text_input(
                "Target Path",
                value=st.session_state.target_path or str(settings.nas_path),
                help="출력 파일을 저장할 NAS 경로",
                label_visibility="collapsed",
            )
        with target_col2:
            if is_tkinter_available():
                if st.button("📁", help="폴더 선택", key="browse_target"):
                    folder = select_folder(
                        title="출력 폴더 선택",
                        initial_dir=target_input or str(Path.cwd()),
                    )
                    if folder:
                        st.session_state.target_path = folder
                        st.rerun()

        if target_input != st.session_state.target_path:
            st.session_state.target_path = target_input

        # === Interval Setting ===
        st.subheader("⏱️ 설정")

        interval = st.number_input(
            "생성 간격 (초)",
            value=settings.interval_sec,
            min_value=1,
            max_value=300,
            help="핸드 생성 간격 (초)",
        )

        st.divider()

        # === Control Buttons ===
        col1, col2 = st.columns(2)

        with col1:
            start_disabled = (
                st.session_state.simulator is not None
                and st.session_state.simulator.status == Status.RUNNING
            ) or not st.session_state.selected_files
            if st.button(
                "▶️ 시작", disabled=start_disabled, use_container_width=True
            ):
                source = Path(st.session_state.source_path)
                target = Path(st.session_state.target_path)

                if not source.exists():
                    st.error(f"Source path not found: {source}")
                elif not st.session_state.target_path:
                    st.error("Target path is required")
                else:
                    # Create simulator with selected files
                    st.session_state.simulator = GFXJsonSimulator(
                        source_path=source,
                        target_path=target,
                        interval=interval,
                    )
                    # Override discovered files with selected ones
                    selected_paths = [
                        Path(f["path"]) for f in st.session_state.selected_files
                    ]
                    st.session_state.simulator._selected_files = selected_paths

                    st.session_state.thread = threading.Thread(
                        target=run_simulation_thread,
                        args=(st.session_state.simulator,),
                        daemon=True,
                    )
                    st.session_state.thread.start()
                    st.rerun()

        with col2:
            stop_disabled = (
                st.session_state.simulator is None
                or st.session_state.simulator.status != Status.RUNNING
            )
            if st.button("⏹️ 정지", disabled=stop_disabled, use_container_width=True):
                if st.session_state.simulator:
                    st.session_state.simulator.stop()
                    st.rerun()

        # Reset button
        if st.button("🔄 초기화", use_container_width=True):
            st.session_state.simulator = None
            st.session_state.thread = None
            st.session_state.scanned_files = []
            st.session_state.selected_files = []
            st.rerun()

    # === Main Content ===

    # File selection section
    if st.session_state.scanned_files:
        st.header("📋 파일 선택")

        # Group files by table
        tables: dict[str, list[dict[str, Any]]] = {}
        for f in st.session_state.scanned_files:
            table = f["table"] or "기타"
            if table not in tables:
                tables[table] = []
            tables[table].append(f)

        # Display selection
        col1, col2 = st.columns([2, 1])

        with col1:
            # Create tabs for each table
            if len(tables) > 1:
                tab_names = list(tables.keys())
                tabs = st.tabs(tab_names)

                all_selected: list[dict[str, Any]] = []
                for tab, table_name in zip(tabs, tab_names):
                    with tab:
                        table_files = tables[table_name]

                        # Select all checkbox for this table
                        select_all = st.checkbox(
                            f"전체 선택 ({len(table_files)}개)",
                            key=f"select_all_{table_name}",
                        )

                        for f in table_files:
                            display = format_file_display(f)
                            selected = st.checkbox(
                                display,
                                value=select_all
                                or f in st.session_state.selected_files,
                                key=f"file_{f['path']}",
                            )
                            if selected:
                                all_selected.append(f)

                st.session_state.selected_files = all_selected
            else:
                # Single table - simpler display
                table_name = list(tables.keys())[0]
                table_files = tables[table_name]

                select_all = st.checkbox(f"전체 선택 ({len(table_files)}개)")

                all_selected = []
                for f in table_files:
                    display = format_file_display(f)
                    selected = st.checkbox(
                        display,
                        value=select_all or f in st.session_state.selected_files,
                        key=f"file_{f['path']}",
                    )
                    if selected:
                        all_selected.append(f)

                st.session_state.selected_files = all_selected

        with col2:
            st.markdown("### 선택 요약")
            total_files = len(st.session_state.selected_files)
            total_hands = sum(f["hand_count"] for f in st.session_state.selected_files)
            total_size = sum(f["size_kb"] for f in st.session_state.selected_files)

            st.metric("선택된 파일", f"{total_files}개")
            st.metric("총 핸드 수", f"{total_hands}개")
            st.metric("총 크기", f"{total_size:.1f} KB")

            if total_hands > 0 and interval > 0:
                est_time = total_hands * interval
                st.metric("예상 소요 시간", format_duration(est_time))

    # Simulator status section
    simulator = st.session_state.simulator

    if simulator is None:
        if not st.session_state.scanned_files:
            st.info("👆 좌측에서 소스 경로를 지정하고 '파일 스캔' 버튼을 클릭하세요.")
        elif not st.session_state.selected_files:
            st.info("👆 시뮬레이션할 파일을 선택하세요.")
        return

    # Status display
    st.divider()
    status_colors = {
        Status.IDLE: "🔵",
        Status.RUNNING: "🟢",
        Status.PAUSED: "🟡",
        Status.STOPPED: "🟠",
        Status.COMPLETED: "✅",
        Status.ERROR: "❌",
    }
    status_icon = status_colors.get(simulator.status, "⚪")
    st.subheader(f"{status_icon} 상태: {simulator.status.value.upper()}")

    # Progress section
    st.header("📊 진행 상황")

    progress = simulator.progress
    progress_pct = progress.progress

    # Progress bar
    st.progress(progress_pct)

    # Metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "현재 핸드",
            f"{progress.current_hand} / {progress.total_hands}",
        )

    with col2:
        st.metric(
            "진행률",
            f"{progress_pct * 100:.1f}%",
        )

    with col3:
        st.metric(
            "경과 시간",
            format_duration(progress.elapsed_seconds),
        )

    with col4:
        st.metric(
            "예상 남은 시간",
            format_duration(progress.remaining_seconds),
        )

    if progress.current_file:
        st.caption(f"📁 현재 파일: {progress.current_file}")

    # Logs section
    st.header("📝 실시간 로그")

    logs = simulator.get_logs(limit=50)

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
        st.caption("로그가 없습니다.")

    # Auto-refresh while running
    if simulator.status == Status.RUNNING:
        time.sleep(1)
        st.rerun()


if __name__ == "__main__":
    main()
