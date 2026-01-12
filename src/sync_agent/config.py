"""SyncAgent 설정."""
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SyncAgentSettings(BaseSettings):
    """SyncAgent 설정.

    환경변수 또는 config.env 파일에서 설정을 로드합니다.
    """

    model_config = SettingsConfigDict(
        env_file="config.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase 연결 (필수)
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")

    # 감시 경로
    gfx_watch_path: str = Field(default="C:/GFX/output", alias="GFX_WATCH_PATH")

    # 로컬 큐 설정
    queue_db_path: str = Field(
        default="C:/GFX/sync_queue/pending.db", alias="QUEUE_DB_PATH"
    )

    # 동기화 설정
    file_settle_delay: float = Field(default=2.0)
    retry_delay: float = Field(default=5.0)
    max_retries: int = Field(default=5)
    queue_process_interval: int = Field(default=60)

    # 로깅
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_path: str = Field(
        default="C:/GFX/logs/sync_agent.log", alias="LOG_PATH"
    )

    @field_validator("gfx_watch_path", "queue_db_path", "log_path")
    @classmethod
    def normalize_path(cls, v: str) -> str:
        """경로 정규화 (백슬래시 → 슬래시)."""
        return str(Path(v).as_posix())
