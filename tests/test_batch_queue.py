"""BatchQueue 단위 테스트.

FT-0011: NAS JSON → Supabase 최적화 동기화 시스템
"""

import asyncio

import pytest

from src.sync_agent.batch_queue import BatchQueue


class TestBatchQueue:
    """BatchQueue 테스트 클래스."""

    async def test_add_single_record_no_flush(self) -> None:
        """단일 레코드 추가 시 플러시 안됨."""
        queue = BatchQueue(max_size=500, flush_interval=5.0)

        result = await queue.add({"id": 1})

        assert result is None
        assert queue.pending_count == 1

    async def test_add_triggers_flush_at_max_size(self) -> None:
        """max_size 도달 시 플러시 트리거."""
        queue = BatchQueue(max_size=5, flush_interval=10.0)

        # 4개 추가 - 플러시 안됨
        for i in range(4):
            result = await queue.add({"id": i})
            assert result is None

        assert queue.pending_count == 4

        # 5번째에서 플러시
        result = await queue.add({"id": 4})

        assert result is not None
        assert len(result) == 5
        assert queue.pending_count == 0
        assert queue.is_empty

    async def test_add_triggers_flush_at_interval(self) -> None:
        """시간 경과 시 플러시 트리거."""
        queue = BatchQueue(max_size=1000, flush_interval=0.1)

        # 첫 번째 레코드 추가
        result = await queue.add({"id": 1})
        assert result is None

        # 시간 대기
        await asyncio.sleep(0.15)

        # 두 번째 레코드 추가 시 시간 기반 플러시
        result = await queue.add({"id": 2})

        assert result is not None
        assert len(result) == 2
        assert queue.is_empty

    async def test_flush_returns_all_items(self) -> None:
        """강제 플러시 시 모든 아이템 반환."""
        queue = BatchQueue(max_size=500, flush_interval=10.0)

        await queue.add({"id": 1})
        await queue.add({"id": 2})
        await queue.add({"id": 3})

        assert queue.pending_count == 3

        result = await queue.flush()

        assert len(result) == 3
        assert queue.is_empty

    async def test_flush_empty_queue(self) -> None:
        """빈 큐 플러시 시 빈 리스트 반환."""
        queue = BatchQueue()

        result = await queue.flush()

        assert result == []
        assert queue.is_empty

    async def test_pending_count(self) -> None:
        """pending_count 정확성."""
        queue = BatchQueue(max_size=100)

        assert queue.pending_count == 0

        await queue.add({"id": 1})
        assert queue.pending_count == 1

        await queue.add({"id": 2})
        assert queue.pending_count == 2

        await queue.flush()
        assert queue.pending_count == 0

    async def test_is_empty_property(self) -> None:
        """is_empty 속성 테스트."""
        queue = BatchQueue()

        assert queue.is_empty is True

        await queue.add({"id": 1})
        assert queue.is_empty is False

        await queue.flush()
        assert queue.is_empty is True

    async def test_seconds_since_last_flush(self) -> None:
        """마지막 플러시 이후 경과 시간."""
        queue = BatchQueue()

        # 초기 시간
        initial = queue.seconds_since_last_flush
        assert initial >= 0

        await asyncio.sleep(0.1)

        # 시간 경과 확인
        assert queue.seconds_since_last_flush > initial

        # 플러시 후 리셋
        await queue.flush()
        assert queue.seconds_since_last_flush < 0.1

    async def test_get_stats(self) -> None:
        """통계 정보 반환."""
        queue = BatchQueue(max_size=100, flush_interval=5.0)

        await queue.add({"id": 1})
        await queue.add({"id": 2})

        stats = queue.get_stats()

        assert stats["pending_count"] == 2
        assert stats["max_size"] == 100
        assert stats["flush_interval"] == 5.0
        assert "seconds_since_last_flush" in stats
        assert stats["is_empty"] is False

    async def test_concurrent_adds(self) -> None:
        """동시 추가 시 락 보호 테스트."""
        queue = BatchQueue(max_size=1000, flush_interval=10.0)

        async def add_items(start: int, count: int) -> None:
            for i in range(count):
                await queue.add({"id": start + i})

        # 동시에 100개씩 3번 추가
        await asyncio.gather(
            add_items(0, 100),
            add_items(100, 100),
            add_items(200, 100),
        )

        assert queue.pending_count == 300

    async def test_record_preservation(self) -> None:
        """레코드 내용 보존 테스트."""
        queue = BatchQueue(max_size=2)

        record1 = {"id": 1, "name": "test1", "data": {"nested": True}}
        record2 = {"id": 2, "name": "test2", "data": {"nested": False}}

        await queue.add(record1)
        result = await queue.add(record2)

        assert result is not None
        assert result[0] == record1
        assert result[1] == record2

    async def test_multiple_flush_cycles(self) -> None:
        """여러 플러시 사이클 테스트."""
        queue = BatchQueue(max_size=2, flush_interval=10.0)

        # 첫 번째 사이클
        await queue.add({"cycle": 1, "item": 1})
        result1 = await queue.add({"cycle": 1, "item": 2})
        assert result1 is not None
        assert len(result1) == 2

        # 두 번째 사이클
        await queue.add({"cycle": 2, "item": 1})
        result2 = await queue.add({"cycle": 2, "item": 2})
        assert result2 is not None
        assert len(result2) == 2

        # 결과 독립성 확인
        assert result1[0]["cycle"] == 1
        assert result2[0]["cycle"] == 2


class TestBatchQueueEdgeCases:
    """BatchQueue 엣지 케이스 테스트."""

    async def test_max_size_one(self) -> None:
        """max_size=1 테스트."""
        queue = BatchQueue(max_size=1)

        result = await queue.add({"id": 1})

        assert result is not None
        assert len(result) == 1

    async def test_very_short_flush_interval(self) -> None:
        """매우 짧은 flush_interval 테스트."""
        queue = BatchQueue(max_size=1000, flush_interval=0.01)

        await queue.add({"id": 1})
        await asyncio.sleep(0.02)
        result = await queue.add({"id": 2})

        assert result is not None

    async def test_large_batch(self) -> None:
        """대용량 배치 테스트."""
        queue = BatchQueue(max_size=1000)

        for i in range(999):
            await queue.add({"id": i})

        assert queue.pending_count == 999

        result = await queue.add({"id": 999})

        assert result is not None
        assert len(result) == 1000
