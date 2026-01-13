"""SyncService 테스트."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    def mock_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> SyncAgentSettings:
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

    def test_prepare_record(
        self, sync_service: SyncService, sample_gfx_json: Path
    ) -> None:
        """레코드 준비 테스트."""
        record = sync_service._prepare_record(sample_gfx_json)

        assert record["session_id"] == "game_123"
        assert record["file_name"] == sample_gfx_json.name
        assert record["table_type"] == "Tournament"
        assert record["event_title"] == "WSOP Main Event"
        assert record["hand_count"] == 2
        assert record["sync_source"] == "gfx_pc_direct"
        assert record["sync_status"] == "synced"
        assert "file_hash" in record
        assert len(record["file_hash"]) == 64

    async def test_sync_file_realtime_success(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
    ) -> None:
        """실시간 동기화(created 이벤트) 성공."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # upsert 성공
            mock_supabase_client.table.return_value.upsert.return_value.execute.return_value = (
                MagicMock(data=[{"id": 1}])
            )

            result = await sync_service.sync_file(str(sample_gfx_json), "created")

            assert result.success is True
            assert result.session_id == "game_123"
            assert result.hand_count == 2
            assert result.queued is False
            assert result.error_message is None

            # upsert가 호출되었는지 확인
            mock_supabase_client.table.return_value.upsert.assert_called_once()

    async def test_sync_file_batch_queue(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
    ) -> None:
        """배치 큐(modified 이벤트) 성공."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            result = await sync_service.sync_file(str(sample_gfx_json), "modified")

            assert result.success is True
            assert result.session_id == "game_123"
            assert result.hand_count == 2
            assert result.queued is True  # 배치 큐에 추가됨

    async def test_sync_file_queue_on_error(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
        local_queue: LocalQueue,
    ) -> None:
        """연결 오류 시 로컬 큐에 저장."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # upsert 실패
            mock_supabase_client.table.return_value.upsert.return_value.execute.side_effect = Exception(
                "Connection error"
            )

            result = await sync_service.sync_file(str(sample_gfx_json), "created")

            assert result.success is False
            assert result.queued is True
            assert "Connection error" in (result.error_message or "")

            # 큐에 추가되었는지 확인
            stats = local_queue.get_stats()
            assert stats["pending"] == 1

    async def test_process_offline_queue_success(
        self,
        sync_service: SyncService,
        mock_supabase_client: MagicMock,
        local_queue: LocalQueue,
        sample_gfx_json: Path,
    ) -> None:
        """오프라인 큐 배치 처리 성공."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 큐에 항목 추가
            local_queue.enqueue(str(sample_gfx_json), "created")

            # upsert 성공
            mock_supabase_client.table.return_value.upsert.return_value.execute.return_value = (
                MagicMock(data=[{"id": 1}])
            )

            success_count = await sync_service.process_offline_queue()

            assert success_count == 1

            # 큐에서 완료 처리되었는지 확인
            stats = local_queue.get_stats()
            assert stats["completed"] == 1
            assert stats["pending"] == 0

    async def test_process_offline_queue_batch_failure(
        self,
        sync_service: SyncService,
        mock_supabase_client: MagicMock,
        local_queue: LocalQueue,
        sample_gfx_json: Path,
        tmp_path: Path,
    ) -> None:
        """오프라인 큐 배치 처리 실패 시 재시도 카운트 증가."""
        # 두 번째 파일 생성
        file2 = tmp_path / "file2.json"
        file2.write_text(json.dumps({"ID": "game_456", "Hands": []}))

        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # 큐에 2개 추가
            local_queue.enqueue(str(sample_gfx_json), "created")
            local_queue.enqueue(str(file2), "created")

            # upsert 실패
            mock_supabase_client.table.return_value.upsert.return_value.execute.side_effect = Exception(
                "Network error"
            )

            success_count = await sync_service.process_offline_queue()

            # 배치 실패로 0건 처리
            assert success_count == 0

            # 원본 아이템들의 재시도 카운트가 증가했어야 함
            # (배치 실패 시 로컬 큐에 다시 enqueue되므로 총 4개가 됨)
            pending = local_queue.get_pending(limit=10)
            # 최소 2개 이상 pending 상태
            assert len(pending) >= 2

            # 원본 항목(id=1, 2)의 retry_count가 증가했는지 확인
            original_items = [item for item in pending if item.id in (1, 2)]
            assert len(original_items) == 2
            for item in original_items:
                assert item.retry_count == 1

    async def test_flush_batch_queue(
        self,
        sync_service: SyncService,
        sample_gfx_json: Path,
        mock_supabase_client: MagicMock,
    ) -> None:
        """배치 큐 강제 플러시."""
        with patch("src.sync_agent.sync_service.create_client") as mock_create:
            mock_create.return_value = mock_supabase_client

            # modified 이벤트로 배치 큐에 추가
            await sync_service.sync_file(str(sample_gfx_json), "modified")

            # 배치 큐에 항목이 있는지 확인
            assert sync_service.batch_queue.pending_count == 1

            # upsert 성공
            mock_supabase_client.table.return_value.upsert.return_value.execute.return_value = (
                MagicMock(data=[{"id": 1}])
            )

            # 강제 플러시
            count = await sync_service.flush_batch_queue()

            assert count == 1
            assert sync_service.batch_queue.pending_count == 0

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
            mock_supabase_client.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception(
                "Connection refused"
            )

            result = await sync_service.health_check()
            assert result is False

    def test_get_stats(
        self, sync_service: SyncService, local_queue: LocalQueue
    ) -> None:
        """서비스 통계 정보."""
        stats = sync_service.get_stats()

        assert "batch_queue" in stats
        assert "offline_queue_pending" in stats
        assert "supabase_url" in stats
        assert stats["supabase_url"] == "https://test.supabase.co"
