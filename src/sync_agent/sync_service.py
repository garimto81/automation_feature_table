"""Supabase 동기화 서비스 - 하이브리드 방식.

FT-0011: NAS JSON → Supabase 최적화 동기화 시스템
- 실시간 경로: created 이벤트 → 단건 Upsert (즉시 처리)
- 배치 경로: modified 이벤트 → BatchQueue (500건 또는 5초)
- 오프라인 큐: 장애 복구 시 배치 처리
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.sync_agent.batch_queue import BatchQueue
from supabase import Client, create_client

if TYPE_CHECKING:
    from src.sync_agent.config import SyncAgentSettings
    from src.sync_agent.local_queue import LocalQueue

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """동기화 결과."""

    success: bool
    session_id: str | None
    hand_count: int
    error_message: str | None = None
    queued: bool = False


class SyncService:
    """Supabase 동기화 서비스 - 하이브리드 방식.

    기능:
    - 실시간 동기화: created 이벤트 → 단건 Upsert
    - 배치 동기화: modified 이벤트 → BatchQueue
    - 오프라인 큐 배치 처리
    - 해시 기반 중복 방지 (upsert on_conflict)
    """

    def __init__(
        self,
        settings: "SyncAgentSettings",
        local_queue: "LocalQueue",
    ) -> None:
        """초기화.

        Args:
            settings: SyncAgent 설정
            local_queue: 로컬 큐 인스턴스
        """
        self.settings = settings
        self.local_queue = local_queue
        self._client: Client | None = None

        # 배치 큐 초기화 (FT-0011)
        self.batch_queue = BatchQueue(
            max_size=settings.batch_size,
            flush_interval=settings.flush_interval,
        )

    @property
    def client(self) -> Client:
        """Lazy Supabase 클라이언트.

        Returns:
            Supabase Client 인스턴스
        """
        if self._client is None:
            self._client = create_client(
                self.settings.supabase_url,
                self.settings.supabase_key,
            )
            logger.info(f"Supabase client created for {self.settings.supabase_url}")

        return self._client

    def _compute_hash(self, file_path: Path | str) -> str:
        """SHA256 해시 계산.

        Args:
            file_path: 파일 경로

        Returns:
            SHA256 hex digest
        """
        path = Path(file_path)
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _prepare_record(self, path: Path) -> dict[str, Any]:
        """Supabase 레코드 준비.

        Args:
            path: 파일 경로

        Returns:
            Supabase 레코드 딕셔너리
        """
        content = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(content)
        file_hash = self._compute_hash(path)

        return {
            "session_id": data.get("ID"),
            "file_name": path.name,
            "file_hash": file_hash,
            "file_path": str(path),  # 배치 실패 시 복구용
            "raw_json": data,
            "table_type": data.get("Type", "UNKNOWN"),
            "event_title": data.get("EventTitle", ""),
            "software_version": data.get("SoftwareVersion", ""),
            "hand_count": len(data.get("Hands", [])),
            "session_created_at": data.get("CreatedDateTimeUTC"),
            "sync_source": "gfx_pc_direct",
            "sync_status": "synced",
        }

    async def sync_file(
        self, file_path: str, event_type: str = "created"
    ) -> SyncResult:
        """파일을 Supabase로 동기화 (이벤트 타입에 따른 라우팅).

        - created: 실시간 단건 Upsert
        - modified: 배치 큐에 추가

        Args:
            file_path: GFX JSON 파일 경로
            event_type: 이벤트 타입 (created/modified)

        Returns:
            SyncResult
        """
        if event_type == "created":
            # 실시간 경로: 즉시 처리
            return await self._sync_realtime(file_path)
        else:
            # 배치 경로: 큐에 추가
            return await self._queue_for_batch(file_path)

    async def _sync_realtime(self, file_path: str) -> SyncResult:
        """실시간 단건 동기화 (created 이벤트용).

        Args:
            file_path: GFX JSON 파일 경로

        Returns:
            SyncResult
        """
        path = Path(file_path)

        try:
            record = self._prepare_record(path)

            # file_path는 Supabase 테이블에 불필요하므로 제거
            record_for_db = {k: v for k, v in record.items() if k != "file_path"}

            # insert → upsert 전환 (중복 시 업데이트)
            self.client.table("gfx_sessions").upsert(
                record_for_db,
                on_conflict="file_hash",
            ).execute()

            logger.info(
                f"Realtime sync: {path.name} (session_id={record['session_id']})"
            )

            return SyncResult(
                success=True,
                session_id=record["session_id"],
                hand_count=record["hand_count"],
                queued=False,
            )

        except Exception as e:
            error_msg = f"Realtime sync failed for {path.name}: {e}"
            logger.error(error_msg)

            # 실패 시 로컬 큐에 저장
            try:
                self.local_queue.enqueue(file_path, "created")
                logger.info(f"File queued for retry: {path.name}")
                queued = True
            except Exception as queue_error:
                logger.error(f"Failed to queue file: {queue_error}")
                queued = False

            return SyncResult(
                success=False,
                session_id=None,
                hand_count=0,
                error_message=error_msg,
                queued=queued,
            )

    async def _queue_for_batch(self, file_path: str) -> SyncResult:
        """배치 큐에 추가 (modified 이벤트용).

        Args:
            file_path: GFX JSON 파일 경로

        Returns:
            SyncResult
        """
        path = Path(file_path)

        try:
            record = self._prepare_record(path)
            batch = await self.batch_queue.add(record)

            # 플러시 조건 충족 시 배치 처리
            if batch:
                await self._execute_batch(batch)

            logger.debug(
                f"Batch queued: {path.name} "
                f"(pending={self.batch_queue.pending_count})"
            )

            return SyncResult(
                success=True,
                session_id=record["session_id"],
                hand_count=record["hand_count"],
                queued=True,
            )

        except Exception as e:
            error_msg = f"Batch queue failed for {path.name}: {e}"
            logger.error(error_msg)

            # 실패 시 로컬 큐에 저장
            try:
                self.local_queue.enqueue(file_path, "modified")
                queued = True
            except Exception:
                queued = False

            return SyncResult(
                success=False,
                session_id=None,
                hand_count=0,
                error_message=error_msg,
                queued=queued,
            )

    async def _execute_batch(self, batch: list[dict[str, Any]]) -> int:
        """배치 Upsert 실행.

        Args:
            batch: 레코드 리스트

        Returns:
            처리된 레코드 수
        """
        if not batch:
            return 0

        try:
            # file_path는 Supabase 테이블에 불필요하므로 제거
            records_for_db = [
                {k: v for k, v in record.items() if k != "file_path"}
                for record in batch
            ]

            response = self.client.table("gfx_sessions").upsert(
                records_for_db,
                on_conflict="file_hash",
            ).execute()

            count = len(response.data)
            logger.info(f"Batch upsert: {count} records")
            return count

        except Exception as e:
            logger.error(f"Batch upsert failed: {e}")

            # 배치 실패 시 개별 레코드를 로컬 큐에 저장
            for record in batch:
                file_path = record.get("file_path")
                if file_path:
                    try:
                        self.local_queue.enqueue(file_path, "modified")
                    except Exception as queue_error:
                        logger.error(f"Failed to queue record: {queue_error}")

            raise

    async def flush_batch_queue(self) -> int:
        """배치 큐 강제 플러시.

        애플리케이션 종료 시 호출.

        Returns:
            처리된 레코드 수
        """
        batch = await self.batch_queue.flush()
        if batch:
            return await self._execute_batch(batch)
        return 0

    async def process_offline_queue(self) -> int:
        """오프라인 큐 배치 처리.

        Returns:
            성공 건수
        """
        pending_items = self.local_queue.get_pending(limit=50)

        if not pending_items:
            return 0

        logger.info(f"Processing {len(pending_items)} queued items")

        # 배치 준비
        batch_records: list[dict[str, Any]] = []
        processed_items: list[tuple[int, str]] = []  # (id, file_path)

        for item in pending_items:
            file_path = Path(item.file_path)

            if not file_path.exists():
                self.local_queue.mark_failed(item.id, f"File not found: {file_path}")
                continue

            try:
                record = self._prepare_record(file_path)
                batch_records.append(record)
                processed_items.append((item.id, str(file_path)))
            except Exception as e:
                logger.warning(f"Record prepare failed for {file_path}: {e}")
                self.local_queue.increment_retry(item.id)

        # 배치 Upsert
        if batch_records:
            try:
                count = await self._execute_batch(batch_records)

                # 성공한 항목 완료 처리
                for item_id, _ in processed_items:
                    self.local_queue.mark_completed(item_id)

                logger.info(f"Queue batch processed: {count} records")
                return count

            except Exception as e:
                logger.error(f"Queue batch failed: {e}")
                # 실패 시 재시도 카운트 증가
                for item_id, _ in processed_items:
                    retry_count = self.local_queue.increment_retry(item_id)
                    if retry_count >= self.settings.max_retries:
                        self.local_queue.mark_failed(
                            item_id, f"Max retries exceeded: {e}"
                        )

        return 0

    async def health_check(self) -> bool:
        """Supabase 연결 확인.

        Returns:
            True if connection is healthy
        """
        try:
            self.client.table("gfx_sessions").select("id").limit(1).execute()
            logger.debug("Supabase health check passed")
            return True
        except Exception as e:
            logger.error(f"Supabase health check failed: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """서비스 통계 정보.

        Returns:
            통계 딕셔너리
        """
        return {
            "batch_queue": self.batch_queue.get_stats(),
            "offline_queue_pending": len(self.local_queue.get_pending(limit=1000)),
            "supabase_url": self.settings.supabase_url,
        }
