"""LocalQueue 테스트."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.sync_agent.local_queue import LocalQueue, QueueItem


class TestLocalQueue:
    """LocalQueue 테스트 클래스."""

    @pytest.fixture
    def queue(self, temp_db_path: Path) -> LocalQueue:
        """LocalQueue 인스턴스."""
        return LocalQueue(temp_db_path)

    def test_init_creates_db(self, tmp_path: Path) -> None:
        """DB 파일 생성."""
        db_path = tmp_path / "new_queue.db"
        assert not db_path.exists()

        queue = LocalQueue(db_path)

        assert db_path.exists()
        assert queue.db_path == db_path
        assert queue.max_retries == 5

    def test_init_with_custom_max_retries(self, tmp_path: Path) -> None:
        """커스텀 max_retries 설정."""
        db_path = tmp_path / "custom_queue.db"
        queue = LocalQueue(db_path, max_retries=10)

        assert queue.max_retries == 10

    def test_enqueue(
        self, queue: LocalQueue, sample_file_path: str, sample_operation: str
    ) -> None:
        """항목 추가."""
        item_id = queue.enqueue(sample_file_path, sample_operation)

        assert isinstance(item_id, int)
        assert item_id > 0

    def test_enqueue_multiple_items(self, queue: LocalQueue) -> None:
        """여러 항목 추가."""
        id1 = queue.enqueue("file1.json", "create")
        id2 = queue.enqueue("file2.json", "update")
        id3 = queue.enqueue("file3.json", "delete")

        assert id1 != id2 != id3
        assert id1 < id2 < id3  # Auto-increment 확인

    def test_get_pending(
        self, queue: LocalQueue, sample_file_path: str, sample_operation: str
    ) -> None:
        """대기 항목 조회."""
        queue.enqueue(sample_file_path, sample_operation)

        pending = queue.get_pending()

        assert len(pending) == 1
        assert isinstance(pending[0], QueueItem)
        assert pending[0].file_path == sample_file_path
        assert pending[0].operation == sample_operation
        assert pending[0].status == "pending"
        assert pending[0].retry_count == 0
        assert pending[0].error_message is None

    def test_get_pending_fifo_order(self, queue: LocalQueue) -> None:
        """FIFO 순서."""
        queue.enqueue("file1.json", "create")
        queue.enqueue("file2.json", "update")
        queue.enqueue("file3.json", "delete")

        pending = queue.get_pending()

        assert len(pending) == 3
        assert pending[0].file_path == "file1.json"
        assert pending[1].file_path == "file2.json"
        assert pending[2].file_path == "file3.json"

    def test_get_pending_limit(self, queue: LocalQueue) -> None:
        """limit 파라미터."""
        for i in range(10):
            queue.enqueue(f"file{i}.json", "create")

        pending = queue.get_pending(limit=5)

        assert len(pending) == 5
        assert pending[0].file_path == "file0.json"
        assert pending[4].file_path == "file4.json"

    def test_get_pending_excludes_completed(self, queue: LocalQueue) -> None:
        """완료 항목 제외."""
        id1 = queue.enqueue("file1.json", "create")
        queue.enqueue("file2.json", "update")

        queue.mark_completed(id1)

        pending = queue.get_pending()

        assert len(pending) == 1
        assert pending[0].file_path == "file2.json"

    def test_get_pending_excludes_failed(self, queue: LocalQueue) -> None:
        """실패 항목 제외."""
        id1 = queue.enqueue("file1.json", "create")
        queue.enqueue("file2.json", "update")

        queue.mark_failed(id1, "Network error")

        pending = queue.get_pending()

        assert len(pending) == 1
        assert pending[0].file_path == "file2.json"

    def test_mark_completed(self, queue: LocalQueue) -> None:
        """완료 처리."""
        item_id = queue.enqueue("file.json", "create")

        queue.mark_completed(item_id)

        pending = queue.get_pending()
        assert len(pending) == 0

        # 통계로 확인
        stats = queue.get_stats()
        assert stats["completed"] == 1
        assert stats["pending"] == 0

    def test_mark_failed(self, queue: LocalQueue) -> None:
        """실패 처리."""
        item_id = queue.enqueue("file.json", "create")
        error_message = "Connection timeout"

        queue.mark_failed(item_id, error_message)

        pending = queue.get_pending()
        assert len(pending) == 0

        # 통계로 확인
        stats = queue.get_stats()
        assert stats["failed"] == 1
        assert stats["pending"] == 0

    def test_increment_retry(self, queue: LocalQueue) -> None:
        """재시도 카운트."""
        item_id = queue.enqueue("file.json", "create")

        # 첫 번째 재시도
        new_count = queue.increment_retry(item_id)
        assert new_count == 1

        # 두 번째 재시도
        new_count = queue.increment_retry(item_id)
        assert new_count == 2

        # pending에서 재시도 카운트 확인
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 2

    def test_get_pending_excludes_max_retries(self, queue: LocalQueue) -> None:
        """최대 재시도 초과 제외."""
        item_id = queue.enqueue("file.json", "create")

        # max_retries(5)까지 증가
        for _ in range(5):
            queue.increment_retry(item_id)

        # 더 이상 pending에 나타나지 않아야 함
        pending = queue.get_pending()
        assert len(pending) == 0

    def test_get_pending_includes_below_max_retries(self, queue: LocalQueue) -> None:
        """최대 재시도 미만은 포함."""
        item_id = queue.enqueue("file.json", "create")

        # max_retries(5) 미만
        for _ in range(4):
            queue.increment_retry(item_id)

        # 여전히 pending에 포함
        pending = queue.get_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 4

    def test_get_stats(self, queue: LocalQueue) -> None:
        """통계 조회."""
        # 초기 상태
        stats = queue.get_stats()
        assert stats["pending"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0

        # 항목 추가
        id1 = queue.enqueue("file1.json", "create")
        id2 = queue.enqueue("file2.json", "update")
        queue.enqueue("file3.json", "delete")  # id3 사용하지 않음

        stats = queue.get_stats()
        assert stats["pending"] == 3
        assert stats["completed"] == 0
        assert stats["failed"] == 0

        # 완료 처리
        queue.mark_completed(id1)

        stats = queue.get_stats()
        assert stats["pending"] == 2
        assert stats["completed"] == 1
        assert stats["failed"] == 0

        # 실패 처리
        queue.mark_failed(id2, "Error")

        stats = queue.get_stats()
        assert stats["pending"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1

    def test_queue_item_dataclass(self) -> None:
        """QueueItem 데이터클래스."""
        now = datetime.now(UTC)
        item = QueueItem(
            id=1,
            file_path="test.json",
            operation="create",
            created_at=now,
            retry_count=0,
            status="pending",
            error_message=None,
        )

        assert item.id == 1
        assert item.file_path == "test.json"
        assert item.operation == "create"
        assert item.created_at == now
        assert item.retry_count == 0
        assert item.status == "pending"
        assert item.error_message is None

    def test_queue_item_with_error(self) -> None:
        """QueueItem with error."""
        now = datetime.now(UTC)
        error_msg = "Network timeout"
        item = QueueItem(
            id=1,
            file_path="test.json",
            operation="create",
            created_at=now,
            retry_count=3,
            status="failed",
            error_message=error_msg,
        )

        assert item.retry_count == 3
        assert item.status == "failed"
        assert item.error_message == error_msg

    def test_concurrent_enqueue(self, queue: LocalQueue) -> None:
        """동시 enqueue (기본 sqlite 동시성 테스트)."""
        import concurrent.futures

        def enqueue_item(i: int) -> int:
            return queue.enqueue(f"file{i}.json", "create")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            ids = list(executor.map(enqueue_item, range(10)))

        # 모든 ID가 고유해야 함
        assert len(set(ids)) == 10

        # 모든 항목이 pending에 있어야 함
        pending = queue.get_pending(limit=100)
        assert len(pending) == 10

    def test_db_path_as_string(self, tmp_path: Path) -> None:
        """DB 경로를 문자열로 전달."""
        db_path_str = str(tmp_path / "string_path.db")
        queue = LocalQueue(db_path_str)

        assert queue.db_path == Path(db_path_str)
        assert queue.db_path.exists()

    def test_enqueue_returns_sequential_ids(self, queue: LocalQueue) -> None:
        """Sequential ID 반환."""
        ids = [queue.enqueue(f"file{i}.json", "create") for i in range(5)]

        for i in range(len(ids) - 1):
            assert ids[i + 1] == ids[i] + 1
