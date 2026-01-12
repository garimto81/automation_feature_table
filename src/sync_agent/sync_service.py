"""Supabase 동기화 서비스."""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    """Supabase 동기화 서비스.

    기능:
    - GFX JSON 파일을 Supabase로 동기화
    - 해시 기반 중복 방지
    - 실패 시 LocalQueue에 저장
    - 오프라인 큐 처리
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

    async def _is_duplicate(self, file_hash: str) -> bool:
        """해시로 중복 확인.

        Args:
            file_hash: 파일 해시

        Returns:
            True if duplicate exists
        """
        try:
            response = (
                self.client.table("gfx_sessions")
                .select("file_hash")
                .eq("file_hash", file_hash)
                .execute()
            )
            return len(response.data) > 0
        except Exception as e:
            logger.warning(f"Duplicate check failed: {e}")
            # 확인 실패 시 중복 아님으로 처리 (업로드 시도)
            return False

    async def sync_file(
        self, file_path: str, operation: str = "created"
    ) -> SyncResult:
        """파일을 Supabase로 동기화.

        1. 파일 읽기 및 해시 계산
        2. 중복 확인
        3. Supabase 업로드 (gfx_sessions 테이블)
        4. 실패 시 LocalQueue에 저장

        Args:
            file_path: GFX JSON 파일 경로
            operation: 작업 타입 (created/modified)

        Returns:
            SyncResult
        """
        path = Path(file_path)

        try:
            # 1. 파일 읽기 및 파싱
            content = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(content)

            # 2. 해시 계산
            file_hash = self._compute_hash(path)

            # 3. 중복 체크
            if await self._is_duplicate(file_hash):
                logger.info(f"Duplicate file skipped: {path.name}")
                return SyncResult(
                    success=True,
                    session_id=data.get("ID"),
                    hand_count=len(data.get("Hands", [])),
                    queued=False,
                )

            # 4. Supabase 레코드 구성
            record = {
                "session_id": data.get("ID"),
                "file_name": path.name,
                "file_hash": file_hash,
                "raw_json": data,
                "table_type": data.get("Type", "UNKNOWN"),
                "event_title": data.get("EventTitle", ""),
                "software_version": data.get("SoftwareVersion", ""),
                "hand_count": len(data.get("Hands", [])),
                "session_created_at": data.get("CreatedDateTimeUTC"),
                "sync_source": "gfx_pc_direct",
                "sync_status": "synced",
            }

            # 5. 업로드
            self.client.table("gfx_sessions").insert(record).execute()

            logger.info(
                f"File synced successfully: {path.name} (session_id={record['session_id']})"
            )

            return SyncResult(
                success=True,
                session_id=record["session_id"],
                hand_count=record["hand_count"],
                queued=False,
            )

        except Exception as e:
            error_msg = f"Sync failed for {path.name}: {e}"
            logger.error(error_msg)

            # LocalQueue에 추가
            try:
                self.local_queue.enqueue(file_path, operation)
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

    async def process_offline_queue(self) -> int:
        """오프라인 큐 처리.

        Returns:
            성공 건수
        """
        success_count = 0
        pending_items = self.local_queue.get_pending(limit=50)

        logger.info(f"Processing {len(pending_items)} queued items")

        for item in pending_items:
            # 파일이 존재하는지 확인
            file_path = Path(item.file_path)
            if not file_path.exists():
                logger.warning(f"Queued file not found: {file_path}")
                self.local_queue.mark_failed(
                    item.id, f"File not found: {file_path}"
                )
                continue

            # 동기화 재시도
            result = await self.sync_file(str(file_path), item.operation)

            if result.success:
                self.local_queue.mark_completed(item.id)
                success_count += 1
                logger.info(f"Queued file synced: {file_path.name}")
            else:
                # 재시도 카운트 증가
                retry_count = self.local_queue.increment_retry(item.id)

                if retry_count >= self.settings.max_retries:
                    self.local_queue.mark_failed(
                        item.id, f"Max retries exceeded: {result.error_message}"
                    )
                    logger.error(
                        f"Queued file failed after {retry_count} retries: {file_path.name}"
                    )
                else:
                    logger.warning(
                        f"Queued file retry "
                        f"{retry_count}/{self.settings.max_retries}: {file_path.name}"
                    )

        logger.info(f"Queue processing completed: {success_count} succeeded")
        return success_count

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
