"""SyncService 테스트."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sync_agent.config import SyncAgentSettings
from src.sync_agent.local_queue import LocalQueue
from src.sync_agent.sync_service import SyncResult, SyncService


class TestSyncService:
    """SyncService 테스트."""

    @pytest.fixture
    def sample_gfx_json(self, tmp_path: Path) -> Path:
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
    def mock_settings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SyncAgentSettings:
        """Mock 설정."""
        # 환경변수 설정
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test_key")
        monkeypatch.setenv("GFX_WATCH_PATH", str(tmp_path / "gfx_output"))
        monkeypatch.setenv("QUEUE_DB_PATH", str(tmp_path / "test_queue.db"))

        # config.env 파일 없이 환경변수에서만 로드
        return SyncAgentSettings(_env_file=None)

    @pytest.fixture
    def local_queue(self, tmp_path: Path) -> LocalQueue:
        """LocalQueue fixture."""
        return LocalQueue(db_path=tmp_path / "queue.db", max_retries=5)

    @pytest.fixture
    def mock_supabase_client(self) -> MagicMock:
        """Mock Supabase 클라이언트."""
        client = MagicMock()
        # health_check용 select 메서드 체인
        client.table.return_value.select.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"id": 1}])
        )
        return client

    @pytest.fixture
    def sync_service(
        self, mock_settings: SyncAgentSettings, local_queue: LocalQueue
    ) -> SyncService:
        """SyncService fixture."""
        return SyncService(settings=mock_settings, local_queue=local_queue)

    def test_compute_hash(
        self, sync_service: SyncService, sample_gfx_json: Path
    ) -> None:
        """SHA256 해시 계산."""
        hash1 = sync_service._compute_hash(sample_gfx_json)
        hash2 = sync_service._compute_hash(sample_gfx_json)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    async def test_is_duplicate_true(
        self, sync_service: SyncService, mock_supabase_client: MagicMock
    ) -> None:
        """이미 존재하는 해시."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 중복 해시 응답 설정
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[{"file_hash": "abc123"}])
            )

            result = await sync_service._is_duplicate("abc123")
            assert result is True

    async def test_is_duplicate_false(
        self, sync_service: SyncService, mock_supabase_client: MagicMock
    ) -> None:
        """새 해시."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 빈 응답 설정
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            result = await sync_service._is_duplicate("new_hash")
            assert result is False

    async def test_sync_file_success(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
    ) -> None:
        """파일 업로드 성공."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 중복 체크 - 없음
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            # 업로드 성공
            mock_supabase_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[{"id": 1}])
            )

            result = await sync_service.sync_file(str(sample_gfx_json), "created")

            assert result.success is True
            assert result.session_id == "game_123"
            assert result.hand_count == 2
            assert result.queued is False
            assert result.error_message is None

    async def test_sync_file_skip_duplicate(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
    ) -> None:
        """중복 파일 스킵."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 중복 해시 있음
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[{"file_hash": "existing"}])
            )

            result = await sync_service.sync_file(str(sample_gfx_json), "created")

            assert result.success is True
            assert result.session_id == "game_123"
            assert result.hand_count == 2
            assert result.queued is False
            # insert가 호출되지 않아야 함
            mock_supabase_client.table.return_value.insert.assert_not_called()

    async def test_sync_file_queue_on_error(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
        local_queue: LocalQueue,
    ) -> None:
        """연결 오류 시 큐잉."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 중복 체크 통과
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            # 업로드 실패
            mock_supabase_client.table.return_value.insert.return_value.execute.side_effect = (
                Exception("Connection error")
            )

            result = await sync_service.sync_file(str(sample_gfx_json), "created")

            assert result.success is False
            assert result.queued is True
            assert "Connection error" in (result.error_message or "")

            # 큐에 추가되었는지 확인
            stats = local_queue.get_stats()
            assert stats["pending"] == 1

    async def test_process_offline_queue(
        self,
        sync_service: SyncService,
        mock_supabase_client: MagicMock,
        local_queue: LocalQueue,
        sample_gfx_json: Path,
    ) -> None:
        """오프라인 큐 처리."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 큐에 항목 추가
            local_queue.enqueue(str(sample_gfx_json), "created")

            # 중복 체크 통과
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[])
            )

            # 업로드 성공
            mock_supabase_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[{"id": 1}])
            )

            success_count = await sync_service.process_offline_queue()

            assert success_count == 1

            # 큐에서 완료 처리되었는지 확인
            stats = local_queue.get_stats()
            assert stats["completed"] == 1
            assert stats["pending"] == 0

    async def test_process_offline_queue_partial_success(
        self,
        sync_service: SyncService,
        mock_supabase_client: MagicMock,
        local_queue: LocalQueue,
        sample_gfx_json: Path,
        tmp_path: Path,
    ) -> None:
        """큐 처리 - 일부 성공."""
        # 두 번째 파일 생성
        file2 = tmp_path / "file2.json"
        file2.write_text(json.dumps({"ID": "game_456", "Hands": []}))

        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 큐에 2개 추가
            local_queue.enqueue(str(sample_gfx_json), "created")
            local_queue.enqueue(str(file2), "created")

            # 중복 체크는 항상 통과 (빈 리스트 반환)
            # select().eq().execute() 체인에 대한 응답
            duplicate_check_mock = MagicMock()
            duplicate_check_mock.data = []
            mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                duplicate_check_mock
            )

            # insert().execute() - 첫 번째 성공, 두 번째 실패
            mock_supabase_client.table.return_value.insert.return_value.execute.side_effect = [
                MagicMock(data=[{"id": 1}]),
                Exception("Network error"),
            ]

            success_count = await sync_service.process_offline_queue()

            assert success_count == 1

            # 1개 완료, 1개 재시도 대기 (retry_count가 증가했지만 여전히 pending)
            stats = local_queue.get_stats()
            assert stats["completed"] == 1
            # 실패한 두 번째 항목은 여전히 pending
            assert stats["pending"] >= 1
            assert stats["failed"] == 0  # max_retries에 도달하지 않음

    async def test_health_check_success(
        self, sync_service: SyncService, mock_supabase_client: MagicMock
    ) -> None:
        """헬스 체크 성공."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            result = await sync_service.health_check()
            assert result is True

    async def test_health_check_failure(
        self, sync_service: SyncService, mock_supabase_client: MagicMock
    ) -> None:
        """헬스 체크 실패."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 연결 실패 시뮬레이션
            mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = (
                Exception("Connection refused")
            )

            result = await sync_service.health_check()
            assert result is False
