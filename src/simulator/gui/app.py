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

from src.simulator.config import (
    get_last_interval,
    get_last_source_path,
    get_last_target_path,
    get_simulator_settings,
    save_interval,
    save_paths,
)
from src.simulator.gfx_json_simulator import (
    GFXJsonSimulator,
    ParallelSimulationOrchestrator,
    Status,
)
from src.simulator.gui.file_browser import (
    format_file_display,
    is_tkinter_available,
    scan_json_files,
    select_folder,
)
from src.simulator.history import (
    FileStatus,
    RunMode,
    get_history_manager,
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


def run_parallel_simulation_thread(
    orchestrator: ParallelSimulationOrchestrator,
    selected_files: list[Path],
) -> None:
    """Run parallel simulation in background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(orchestrator.run(selected_files))
    finally:
        loop.close()


def render_manual_import_tab() -> None:
    """Render manual import tab for SMB fallback mode (PRD-0010)."""
    st.header("📥 수동 Import")
    st.markdown(
        "SMB 연결 실패 시 수동으로 GFX JSON 파일을 업로드하여 처리할 수 있습니다.\n\n"
        "업로드된 파일은 Fallback 폴더에 저장되어 자동으로 처리됩니다."
    )

    # Get fallback path from settings
    try:
        from src.config.settings import get_settings

        settings = get_settings()
        fallback_path = Path(settings.pokergfx.fallback_path)
    except Exception:
        fallback_path = Path("./data/manual_import")

    # Ensure folder exists
    fallback_path.mkdir(parents=True, exist_ok=True)

    # Display current fallback path
    st.info(f"📁 Fallback 폴더: `{fallback_path.absolute()}`")

    # File uploader
    uploaded_files = st.file_uploader(
        "GFX JSON 파일 업로드",
        type=["json"],
        accept_multiple_files=True,
        help="PokerGFX에서 생성된 JSON 파일을 업로드하세요.",
    )

    if uploaded_files:
        st.subheader("📋 업로드된 파일")

        for i, uploaded_file in enumerate(uploaded_files):
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.text(uploaded_file.name)

            with col2:
                size_kb = len(uploaded_file.getvalue()) / 1024
                st.text(f"{size_kb:.1f} KB")

            with col3:
                # Check if already saved
                save_path = fallback_path / uploaded_file.name
                if save_path.exists():
                    st.warning("이미 존재")
                else:
                    st.success("저장 대기")

        st.divider()

        # Save button
        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 Fallback 폴더에 저장", type="primary", use_container_width=True):
                saved_count = 0
                skipped_count = 0

                for uploaded_file in uploaded_files:
                    save_path = fallback_path / uploaded_file.name

                    if save_path.exists():
                        # Add timestamp suffix to avoid overwrite
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        new_name = f"{save_path.stem}_{timestamp}{save_path.suffix}"
                        save_path = fallback_path / new_name

                    try:
                        save_path.write_bytes(uploaded_file.getvalue())
                        saved_count += 1
                    except Exception as e:
                        st.error(f"저장 실패: {uploaded_file.name} - {e}")
                        skipped_count += 1

                if saved_count > 0:
                    st.success(f"✅ {saved_count}개 파일 저장 완료!")
                if skipped_count > 0:
                    st.warning(f"⚠️ {skipped_count}개 파일 저장 실패")

        with col2:
            if st.button("🗑️ 선택 초기화", use_container_width=True):
                st.rerun()

    # Show existing files in fallback folder
    st.divider()
    st.subheader("📂 Fallback 폴더 내 파일")

    existing_files = list(fallback_path.glob("*.json"))

    if existing_files:
        # Sort by modification time (newest first)
        existing_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        for f in existing_files[:20]:  # Show last 20 files
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.text(f.name)

            with col2:
                size_kb = f.stat().st_size / 1024
                st.text(f"{size_kb:.1f} KB")

            with col3:
                mod_time = datetime.fromtimestamp(f.stat().st_mtime)
                st.text(mod_time.strftime("%H:%M:%S"))

        if len(existing_files) > 20:
            st.caption(f"... 외 {len(existing_files) - 20}개 파일")
    else:
        st.caption("Fallback 폴더에 파일이 없습니다.")


def render_history_tab() -> None:
    """Render the processing history tab."""
    st.header("📊 처리 이력")

    history_mgr = st.session_state.history_manager
    source_path = st.session_state.source_path

    if not source_path:
        st.info("👆 좌측에서 소스 경로를 먼저 설정하세요.")
        return

    # Get records for current source
    records = history_mgr.get_records(source_path)
    # Normalize path separators for comparison
    normalized_source = source_path.replace("\\", "/")
    sessions = [
        s for s in history_mgr.history.sessions
        if s.source_path == source_path
        or s.source_path.replace("\\", "/") == normalized_source
    ]

    # Sessions section
    st.subheader("📁 세션 기록")

    if sessions:
        # Sort by start time (newest first)
        sessions = sorted(sessions, key=lambda s: s.started_at, reverse=True)

        for session in sessions[:10]:
            status_icons = {
                "running": "🟢",
                "paused": "🟡",
                "completed": "✅",
                "stopped": "🟠",
                "error": "❌",
            }
            icon = status_icons.get(session.status, "⚪")

            with st.expander(
                f"{icon} {session.started_at.strftime('%Y-%m-%d %H:%M')} "
                f"({session.files_completed}/{session.files_total} 파일)"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.text(f"세션 ID: {session.session_id[:8]}...")
                    st.text(f"시작: {session.started_at.strftime('%H:%M:%S')}")
                    if session.ended_at:
                        duration = (session.ended_at - session.started_at).total_seconds()
                        st.text(f"종료: {session.ended_at.strftime('%H:%M:%S')}")
                        st.text(f"소요: {format_duration(duration)}")
                with col2:
                    st.text(f"상태: {session.status}")
                    st.text(f"처리: {session.files_completed}/{session.files_total}")
    else:
        st.caption("세션 기록이 없습니다.")

    st.divider()

    # Files section
    st.subheader("📋 파일 처리 기록")

    if records:
        # Sort by processed time (newest first)
        records = sorted(records, key=lambda r: r.processed_at, reverse=True)

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            completed = sum(1 for r in records if r.status == "completed")
            st.metric("완료", f"{completed}개")
        with col2:
            total_hands = sum(r.hand_count for r in records)
            st.metric("총 핸드", f"{total_hands}개")
        with col3:
            total_duration = sum(r.duration_sec for r in records)
            st.metric("총 소요", format_duration(total_duration))

        st.divider()

        # File table
        for record in records[:30]:
            status_icons = {
                "completed": "✅",
                "partial": "⚠️",
                "failed": "❌",
            }
            icon = status_icons.get(record.status, "⚪")
            file_name = Path(record.file_path).name

            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                st.text(f"{icon} {file_name}")
            with col2:
                st.text(f"{record.hand_count} 핸드")
            with col3:
                st.text(record.processed_at.strftime("%m-%d %H:%M"))
            with col4:
                st.text(format_duration(record.duration_sec))

        if len(records) > 30:
            st.caption(f"... 외 {len(records) - 30}개 파일")
    else:
        st.caption("처리 기록이 없습니다.")

    st.divider()

    # Actions
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ 이 소스의 이력 초기화", type="secondary"):
            history_mgr.clear_records(source_path)
            st.success("이력이 초기화되었습니다.")
            st.rerun()
    with col2:
        if st.button("🗑️ 전체 이력 초기화", type="secondary"):
            history_mgr.clear_all()
            st.success("전체 이력이 초기화되었습니다.")
            st.rerun()


def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(
        page_title="GFX JSON Simulator",
        page_icon="🎴",
        layout="wide",
    )

    st.title("🎴 GFX JSON Simulator & Manual Import")
    st.markdown("NAS 테스트를 위한 JSON 파일 시뮬레이터 및 수동 Import")

    # Initialize session state
    if "simulator" not in st.session_state:
        st.session_state.simulator = None
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = None
    if "parallel_mode" not in st.session_state:
        st.session_state.parallel_mode = False
    if "thread" not in st.session_state:
        st.session_state.thread = None
    if "source_path" not in st.session_state:
        # 저장된 경로 로드 (없으면 빈 문자열)
        st.session_state.source_path = get_last_source_path() or ""
    if "target_path" not in st.session_state:
        # 저장된 경로 로드 (없으면 빈 문자열)
        st.session_state.target_path = get_last_target_path() or ""
    if "scanned_files" not in st.session_state:
        st.session_state.scanned_files = []
    if "selected_files" not in st.session_state:
        st.session_state.selected_files = []
    if "saved_interval" not in st.session_state:
        # 저장된 interval 로드
        st.session_state.saved_interval = get_last_interval()
    if "run_mode" not in st.session_state:
        st.session_state.run_mode = RunMode.ALL.value
    if "history_manager" not in st.session_state:
        st.session_state.history_manager = get_history_manager()

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
                        # 폴더 선택 시 영구 저장
                        save_paths(source_path=folder)
                        st.rerun()

        # Update session state and save to file
        if source_input != st.session_state.source_path:
            st.session_state.source_path = source_input
            st.session_state.scanned_files = []
            # 경로 영구 저장
            if source_input:
                save_paths(source_path=source_input)

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
                        # 폴더 선택 시 영구 저장
                        save_paths(target_path=folder)
                        st.rerun()

        # Update session state and save to file
        if target_input != st.session_state.target_path:
            st.session_state.target_path = target_input
            # 경로 영구 저장
            if target_input:
                save_paths(target_path=target_input)

        # === Interval Setting ===
        st.subheader("⏱️ 설정")

        # 저장된 interval이 있으면 사용, 없으면 기본값 사용
        default_interval = st.session_state.saved_interval or settings.interval_sec

        interval = st.number_input(
            "생성 간격 (초)",
            value=default_interval,
            min_value=1,
            max_value=300,
            help="핸드 생성 간격 (초)",
        )

        # Parallel mode toggle
        parallel_mode = st.checkbox(
            "🔀 병렬 시뮬레이션",
            value=st.session_state.parallel_mode,
            help="테이블별로 동시에 처리합니다",
        )
        st.session_state.parallel_mode = parallel_mode

        # Run mode selection
        st.subheader("🎯 실행 모드")

        # Check if checkpoint exists for resume option
        history_mgr = st.session_state.history_manager
        has_checkpoint = history_mgr.load_checkpoint() is not None

        run_mode_options = {
            RunMode.ALL.value: "전체 재실행",
            RunMode.NEW_ONLY.value: "새 파일만",
        }
        if has_checkpoint:
            run_mode_options[RunMode.RESUME.value] = "이어서 실행"

        run_mode = st.radio(
            "실행 모드",
            options=list(run_mode_options.keys()),
            format_func=lambda x: run_mode_options[x],
            index=list(run_mode_options.keys()).index(st.session_state.run_mode)
            if st.session_state.run_mode in run_mode_options
            else 0,
            label_visibility="collapsed",
            help="새 파일만: 이전에 처리하지 않은 파일만 실행\n"
                 "전체 재실행: 모든 선택 파일 실행\n"
                 "이어서 실행: 마지막 checkpoint부터 재개",
        )
        st.session_state.run_mode = run_mode

        st.divider()

        # === Control Buttons ===
        col1, col2 = st.columns(2)

        with col1:
            # Check if running (either simulator or orchestrator)
            is_running = (
                (st.session_state.simulator is not None
                 and st.session_state.simulator.status == Status.RUNNING)
                or (st.session_state.orchestrator is not None
                    and st.session_state.orchestrator.status == Status.RUNNING)
            )
            start_disabled = is_running or not st.session_state.selected_files
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
                    # 시작 시 interval 저장
                    save_interval(interval)
                    st.session_state.saved_interval = interval

                    selected_paths = [
                        Path(f["path"]) for f in st.session_state.selected_files
                    ]

                    # Get selected run mode
                    selected_run_mode = RunMode(st.session_state.run_mode)

                    if st.session_state.parallel_mode:
                        # Parallel mode: use orchestrator
                        st.session_state.orchestrator = ParallelSimulationOrchestrator(
                            source_path=source,
                            target_path=target,
                            interval=interval,
                        )
                        st.session_state.simulator = None

                        st.session_state.thread = threading.Thread(
                            target=run_parallel_simulation_thread,
                            args=(st.session_state.orchestrator, selected_paths),
                            daemon=True,
                        )
                    else:
                        # Sequential mode: use simulator with run_mode
                        st.session_state.simulator = GFXJsonSimulator(
                            source_path=source,
                            target_path=target,
                            interval=interval,
                            run_mode=selected_run_mode,
                        )
                        st.session_state.simulator._selected_files = selected_paths
                        st.session_state.orchestrator = None

                        st.session_state.thread = threading.Thread(
                            target=run_simulation_thread,
                            args=(st.session_state.simulator,),
                            daemon=True,
                        )

                    st.session_state.thread.start()
                    st.rerun()

        with col2:
            # Show different button based on status
            simulator = st.session_state.simulator
            orchestrator = st.session_state.orchestrator

            # Determine active runner
            if simulator and simulator.status == Status.RUNNING:
                # Show pause button when running (sequential mode only)
                if st.button("⏸️ 일시정지", use_container_width=True):
                    simulator.pause()
                    st.rerun()
            elif simulator and simulator.status == Status.PAUSED:
                # Show resume button when paused
                if st.button("▶️ 재개", use_container_width=True):
                    simulator.resume()
                    st.rerun()
            elif orchestrator and orchestrator.status == Status.RUNNING:
                # Parallel mode running - no pause support
                st.button("⏸️ 일시정지", disabled=True, use_container_width=True,
                          help="병렬 모드에서는 일시정지를 지원하지 않습니다")
            else:
                # Show disabled button
                st.button("⏸️ 일시정지", disabled=True, use_container_width=True)

        # Separate stop button for immediate stop
        col3, col4 = st.columns(2)
        with col3:
            # Check if any runner is active
            sim = st.session_state.simulator
            orch = st.session_state.orchestrator
            stop_disabled = not (
                (sim and sim.status in (Status.RUNNING, Status.PAUSED))
                or (orch and orch.status == Status.RUNNING)
            )
            if st.button(
                "⏹️ 정지", disabled=stop_disabled, use_container_width=True, key="stop_btn"
            ):
                if sim:
                    sim.stop()
                if orch:
                    orch.stop()
                st.rerun()

        with col4:
            # Reset button with options
            reset_option = st.selectbox(
                "초기화",
                options=["선택...", "🔄 선택 초기화", "🗑️ 전체 초기화", "📋 이력 초기화"],
                label_visibility="collapsed",
                key="reset_select",
            )

            if reset_option == "🔄 선택 초기화":
                # Reset only selection, keep paths
                st.session_state.simulator = None
                st.session_state.orchestrator = None
                st.session_state.thread = None
                st.session_state.scanned_files = []
                st.session_state.selected_files = []
                st.rerun()
            elif reset_option == "🗑️ 전체 초기화":
                # Full reset including paths
                st.session_state.simulator = None
                st.session_state.orchestrator = None
                st.session_state.thread = None
                st.session_state.scanned_files = []
                st.session_state.selected_files = []
                st.session_state.source_path = ""
                st.session_state.target_path = ""
                st.session_state.run_mode = RunMode.ALL.value
                st.rerun()
            elif reset_option == "📋 이력 초기화":
                # Clear history for current source
                if st.session_state.source_path:
                    history_mgr = st.session_state.history_manager
                    history_mgr.clear_records(st.session_state.source_path)
                    st.success("이력이 초기화되었습니다.")
                    st.rerun()
                else:
                    st.warning("소스 경로를 먼저 설정하세요.")

    # === Main Content with Tabs ===
    main_tab1, main_tab2, main_tab3 = st.tabs(
        ["🎴 시뮬레이터", "📊 처리 이력", "📥 수동 Import"]
    )

    with main_tab3:
        render_manual_import_tab()

    with main_tab2:
        render_history_tab()

    with main_tab1:
        render_simulator_tab(interval)


def get_file_status_display(file_path: str, source_path: str) -> str:
    """Get display string for file processing status."""
    history_mgr = st.session_state.history_manager
    status, record = history_mgr.get_file_status(source_path, Path(file_path))

    if status == FileStatus.NEW:
        return " ✨ 새 파일"
    elif status == FileStatus.PROCESSED_UNCHANGED:
        if record:
            time_str = record.processed_at.strftime("%m-%d %H:%M")
            return f" ⚠️ 처리됨({time_str})"
        return " ⚠️ 처리됨"
    elif status == FileStatus.PROCESSED_CHANGED:
        return " 🔄 변경됨"
    return ""


def render_simulator_tab(interval: float) -> None:
    """Render the simulator tab content."""
    # Get active runner
    simulator = st.session_state.simulator
    orchestrator = st.session_state.orchestrator

    # File selection section
    if st.session_state.scanned_files:
        st.header("📋 파일 선택")

        source_path = st.session_state.source_path

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
                            # Add history status
                            status_display = get_file_status_display(f["path"], source_path)
                            display_with_status = f"{display}{status_display}"

                            selected = st.checkbox(
                                display_with_status,
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
                    # Add history status
                    status_display = get_file_status_display(f["path"], source_path)
                    display_with_status = f"{display}{status_display}"

                    selected = st.checkbox(
                        display_with_status,
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

    # Simulator/Orchestrator status section
    # (simulator and orchestrator already fetched at top of function)

    if simulator is None and orchestrator is None:
        if not st.session_state.scanned_files:
            st.info("👆 좌측에서 소스 경로를 지정하고 '파일 스캔' 버튼을 클릭하세요.")
        elif not st.session_state.selected_files:
            st.info("👆 시뮬레이션할 파일을 선택하세요.")
        return

    # Determine active runner and its status/progress
    if orchestrator is not None:
        active_status = orchestrator.status
        progress = orchestrator.aggregate_progress
        active_logs = orchestrator.get_logs
        mode_label = "🔀 병렬"
    else:
        active_status = simulator.status
        progress = simulator.progress
        active_logs = simulator.get_logs
        mode_label = "📄 순차"

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
    status_icon = status_colors.get(active_status, "⚪")
    st.subheader(f"{status_icon} 상태: {active_status.value.upper()} ({mode_label})")

    # Progress section
    st.header("📊 진행 상황")

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

    logs = active_logs(limit=50)

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

    # Auto-refresh while running or paused
    if active_status in (Status.RUNNING, Status.PAUSED):
        time.sleep(1)
        st.rerun()


if __name__ == "__main__":
    main()
