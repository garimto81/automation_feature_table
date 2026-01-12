"""SyncAgentSettings 테스트."""

import pytest
from pydantic import ValidationError

from src.sync_agent.config import SyncAgentSettings


class TestSyncAgentSettings:
    """SyncAgentSettings 테스트."""

    def test_default_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """기본값 검증."""
        # 필수값만 환경변수로 제공
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key-12345")

        settings = SyncAgentSettings()

        # 기본값 검증
        assert settings.supabase_url == "https://test.supabase.co"
        assert settings.supabase_key == "test-key-12345"
        assert settings.gfx_watch_path == "C:/GFX/output"
        assert settings.queue_db_path == "C:/GFX/sync_queue/pending.db"
        assert settings.file_settle_delay == 2.0
        assert settings.retry_delay == 5.0
        assert settings.max_retries == 5
        assert settings.queue_process_interval == 60
        assert settings.log_level == "INFO"
        assert settings.log_path == "C:/GFX/logs/sync_agent.log"

    def test_env_loading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """환경변수 로드."""
        # 모든 환경변수 설정
        monkeypatch.setenv("SUPABASE_URL", "https://custom.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "custom-key-67890")
        monkeypatch.setenv("GFX_WATCH_PATH", "D:/Custom/GFX")
        monkeypatch.setenv("QUEUE_DB_PATH", "D:/Custom/queue.db")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_PATH", "D:/Custom/logs/sync.log")

        settings = SyncAgentSettings()

        # 환경변수에서 로드된 값 검증
        assert settings.supabase_url == "https://custom.supabase.co"
        assert settings.supabase_key == "custom-key-67890"
        assert settings.gfx_watch_path == "D:/Custom/GFX"
        assert settings.queue_db_path == "D:/Custom/queue.db"
        assert settings.log_level == "DEBUG"
        assert settings.log_path == "D:/Custom/logs/sync.log"

    def test_supabase_url_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """필수값 누락 시 ValidationError."""
        # 환경변수 초기화
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)

        # 필수값 누락 시 ValidationError 발생
        with pytest.raises(ValidationError) as exc_info:
            SyncAgentSettings()

        errors = exc_info.value.errors()
        # alias로 인해 환경변수 이름이 반환됨
        error_fields = {error["loc"][0] for error in errors}
        assert "SUPABASE_URL" in error_fields
        assert "SUPABASE_KEY" in error_fields

    def test_supabase_key_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """supabase_key 누락 시 ValidationError."""
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.delenv("SUPABASE_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            SyncAgentSettings()

        errors = exc_info.value.errors()
        # alias로 인해 환경변수 이름이 반환됨
        error_fields = {error["loc"][0] for error in errors}
        assert "SUPABASE_KEY" in error_fields

    def test_path_normalization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """경로 정규화 (백슬래시 → 슬래시)."""
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")
        monkeypatch.setenv("GFX_WATCH_PATH", "C:\\GFX\\output")
        monkeypatch.setenv("QUEUE_DB_PATH", "C:\\GFX\\queue.db")

        settings = SyncAgentSettings()

        # Windows 경로가 정규화되어야 함
        assert settings.gfx_watch_path == "C:/GFX/output"
        assert settings.queue_db_path == "C:/GFX/queue.db"

    def test_numeric_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """숫자 타입 검증."""
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")

        # 잘못된 타입 제공 시 ValidationError
        with pytest.raises(ValidationError):
            SyncAgentSettings(file_settle_delay="invalid")  # type: ignore

        with pytest.raises(ValidationError):
            SyncAgentSettings(max_retries="not-a-number")  # type: ignore

    def test_extra_fields_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """추가 필드 무시 (extra='ignore')."""
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "test-key")
        monkeypatch.setenv("UNKNOWN_FIELD", "should-be-ignored")

        # 추가 필드가 있어도 에러 없이 생성됨
        settings = SyncAgentSettings()
        assert not hasattr(settings, "unknown_field")
