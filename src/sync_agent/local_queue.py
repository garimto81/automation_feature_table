"""LocalQueue - SQLite 기반 작업 큐."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class QueueItem:
    """큐 항목 데이터 모델."""

    id: int
    file_path: str
    operation: str
    created_at: datetime
    retry_count: int
    status: str
    error_message: str | None = None


class LocalQueue:
    """SQLite 기반 로컬 작업 큐.

    Features:
    - FIFO 순서 보장
    - 재시도 카운트 관리
    - 완료/실패 상태 추적
    - 통계 조회
    """

    def __init__(self, db_path: str | Path, max_retries: int = 5) -> None:
        """초기화.

        Args:
            db_path: SQLite DB 파일 경로
            max_retries: 최대 재시도 횟수 (기본값: 5)
        """
        self.db_path = Path(db_path)
        self.max_retries = max_retries
        self._init_db()

    def _init_db(self) -> None:
        """DB 및 테이블 생성."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    completed_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_retry
                ON queue(status, retry_count)
            """)
            conn.commit()

    def enqueue(self, file_path: str, operation: str) -> int:
        """큐에 추가.

        Args:
            file_path: 파일 경로
            operation: 작업 타입 (create/update/delete)

        Returns:
            생성된 항목의 ID
        """
        created_at = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO queue (file_path, operation, created_at)
                VALUES (?, ?, ?)
                """,
                (file_path, operation, created_at),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore

    def get_pending(self, limit: int = 50) -> list[QueueItem]:
        """대기 항목 조회 (max_retries 미만만).

        Args:
            limit: 최대 조회 개수 (기본값: 50)

        Returns:
            대기 중인 QueueItem 리스트 (FIFO 순서)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, file_path, operation, created_at, retry_count, status, error_message
                FROM queue
                WHERE status = 'pending' AND retry_count < ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (self.max_retries, limit),
            )

            rows = cursor.fetchall()
            return [
                QueueItem(
                    id=row["id"],
                    file_path=row["file_path"],
                    operation=row["operation"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    retry_count=row["retry_count"],
                    status=row["status"],
                    error_message=row["error_message"],
                )
                for row in rows
            ]

    def mark_completed(self, item_id: int) -> None:
        """완료 처리.

        Args:
            item_id: 항목 ID
        """
        completed_at = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE queue
                SET status = 'completed', completed_at = ?
                WHERE id = ?
                """,
                (completed_at, item_id),
            )
            conn.commit()

    def mark_failed(self, item_id: int, error_message: str) -> None:
        """실패 처리.

        Args:
            item_id: 항목 ID
            error_message: 에러 메시지
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE queue
                SET status = 'failed', error_message = ?
                WHERE id = ?
                """,
                (error_message, item_id),
            )
            conn.commit()

    def increment_retry(self, item_id: int) -> int:
        """재시도 카운트 증가.

        Args:
            item_id: 항목 ID

        Returns:
            증가된 재시도 카운트
        """
        with sqlite3.connect(self.db_path) as conn:
            # 현재 retry_count 조회
            cursor = conn.execute(
                "SELECT retry_count FROM queue WHERE id = ?", (item_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Item {item_id} not found")

            current_count: int = int(row[0])
            new_count = current_count + 1

            # retry_count 증가
            conn.execute(
                "UPDATE queue SET retry_count = ? WHERE id = ?", (new_count, item_id)
            )
            conn.commit()

            return new_count

    def get_stats(self) -> dict[str, int]:
        """통계 조회.

        Returns:
            pending, completed, failed 카운트
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM queue
            """)
            row = cursor.fetchone()

            return {
                "pending": row[0] or 0,
                "completed": row[1] or 0,
                "failed": row[2] or 0,
            }
