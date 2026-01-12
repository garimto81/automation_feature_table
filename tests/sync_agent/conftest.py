"""Sync Agent 테스트용 공유 fixtures."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.sync_agent.config import SyncAgentSettings
from src.sync_agent.local_queue import LocalQueue
from src.sync_agent.sync_service import SyncResult, SyncService


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """임시 DB 파일 경로."""
    return tmp_path / "test_queue.db"


@pytest.fixture
def sample_file_path() -> str:
    """샘플 파일 경로."""
    return "//nas/share/poker/session_001.json"


@pytest.fixture
def sample_operation() -> str:
    """샘플 operation."""
    return "create"


@pytest.fixture
def mock_sync_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SyncAgentSettings:
    """SyncService 테스트용 설정."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test_key")
    monkeypatch.setenv("GFX_WATCH_PATH", str(tmp_path / "gfx_output"))
    monkeypatch.setenv("QUEUE_DB_PATH", str(tmp_path / "test_queue.db"))

    return SyncAgentSettings(_env_file=None)


@pytest.fixture
def sample_gfx_json_file(tmp_path: Path) -> Path:
    """샘플 GFX JSON 파일."""
    data = {
        "ID": "game_123",
        "Type": "Tournament",
        "EventTitle": "WSOP Main Event",
        "SoftwareVersion": "3.0.1",
        "CreatedDateTimeUTC": "2026-01-12T10:00:00Z",
        "Hands": [{"HandNumber": 1}, {"HandNumber": 2}],
    }
    file_path = tmp_path / "PGFX_live_data_export GameID=123.json"
    file_path.write_text(json.dumps(data))
    return file_path


@pytest.fixture
def mock_sync_service() -> MagicMock:
    """Mock SyncService for file_handler tests."""
    service = MagicMock()
    service.sync_file = AsyncMock(
        return_value=SyncResult(
            success=True,
            session_id="123",
            hand_count=10,
        )
    )
    service.process_offline_queue = AsyncMock(return_value=0)
    return service
