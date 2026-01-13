"""배치 처리용 인메모리 큐.

FT-0011: NAS JSON → Supabase 최적화 동기화 시스템
- 크기 기반 플러시: max_size 도달 시
- 시간 기반 플러시: flush_interval 초과 시
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BatchQueue:
    """배치 처리용 인메모리 큐.

    속성:
        max_size: 배치 최대 크기 (기본 500)
        flush_interval: 자동 플러시 간격 초 (기본 5.0)

    사용법:
        queue = BatchQueue(max_size=500, flush_interval=5.0)

        # 레코드 추가
        batch = await queue.add({"id": 1, "data": "..."})
        if batch:
            # 플러시 조건 충족 - 배치 처리 실행
            await execute_batch(batch)

        # 강제 플러시 (애플리케이션 종료 시)
        remaining = await queue.flush()
        if remaining:
            await execute_batch(remaining)
    """

    max_size: int = 500
    flush_interval: float = 5.0
    _items: list[dict[str, Any]] = field(default_factory=list)
    _last_flush: float = field(default_factory=time.time)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add(
        self, record: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """레코드 추가. 플러시 조건 충족 시 배치 반환.

        Args:
            record: Supabase 레코드 딕셔너리

        Returns:
            플러시 조건 충족 시 배치 리스트, 아니면 None
        """
        async with self._lock:
            self._items.append(record)

            # 크기 기반 플러시
            if len(self._items) >= self.max_size:
                logger.info(
                    f"BatchQueue: Size threshold reached ({self.max_size}), flushing"
                )
                return await self._flush_internal()

            # 시간 기반 플러시
            if self._should_flush():
                elapsed = time.time() - self._last_flush
                logger.info(
                    f"BatchQueue: Time threshold reached ({elapsed:.1f}s), "
                    f"flushing {len(self._items)} items"
                )
                return await self._flush_internal()

            return None

    def _should_flush(self) -> bool:
        """시간 기반 플러시 조건 확인.

        Returns:
            플러시 필요 여부
        """
        return (
            len(self._items) > 0
            and (time.time() - self._last_flush) >= self.flush_interval
        )

    async def _flush_internal(self) -> list[dict[str, Any]]:
        """내부 플러시 (락 보유 상태에서 호출).

        Returns:
            플러시된 배치 리스트
        """
        batch = self._items
        self._items = []
        self._last_flush = time.time()
        return batch

    async def flush(self) -> list[dict[str, Any]]:
        """강제 플러시.

        애플리케이션 종료 시 또는 명시적 플러시가 필요할 때 호출.

        Returns:
            플러시된 배치 리스트 (빈 리스트일 수 있음)
        """
        async with self._lock:
            if self._items:
                logger.info(f"BatchQueue: Force flushing {len(self._items)} items")
            return await self._flush_internal()

    @property
    def pending_count(self) -> int:
        """대기 중인 레코드 수.

        Returns:
            대기 중인 레코드 개수
        """
        return len(self._items)

    @property
    def is_empty(self) -> bool:
        """큐가 비어있는지 확인.

        Returns:
            빈 큐 여부
        """
        return len(self._items) == 0

    @property
    def seconds_since_last_flush(self) -> float:
        """마지막 플러시 이후 경과 시간.

        Returns:
            경과 시간 (초)
        """
        return time.time() - self._last_flush

    def get_stats(self) -> dict[str, Any]:
        """큐 통계 정보.

        Returns:
            통계 딕셔너리
        """
        return {
            "pending_count": self.pending_count,
            "max_size": self.max_size,
            "flush_interval": self.flush_interval,
            "seconds_since_last_flush": round(self.seconds_since_last_flush, 2),
            "is_empty": self.is_empty,
        }
