"""Application settings using pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PokerGFXSettings(BaseSettings):
    """PokerGFX configuration - WebSocket OR JSON file mode."""

    # Mode selection: "websocket" or "json"
    mode: str = Field(
        default="json",
        alias="POKERGFX_MODE",
        description="Primary source mode: websocket or json",
    )

    # WebSocket mode settings (legacy)
    api_url: str = Field(default="ws://localhost:8080", alias="POKERGFX_API_URL")
    api_key: str = Field(default="", alias="POKERGFX_API_KEY")
    reconnect_interval: int = Field(default=5, description="Reconnect interval in seconds")
    max_retries: int = Field(default=3, description="Maximum reconnection attempts")

    # JSON file mode settings (NAS)
    json_watch_path: str = Field(
        default="",
        alias="POKERGFX_JSON_PATH",
        description="NAS mounted path for JSON files",
    )
    polling_interval: float = Field(
        default=2.0,
        alias="POKERGFX_POLLING_INTERVAL",
        description="File polling interval in seconds (for SMB/NAS)",
    )
    processed_db_path: str = Field(
        default="./data/processed_files.json",
        alias="POKERGFX_PROCESSED_DB",
        description="Path to store processed file records",
    )
    file_pattern: str = Field(
        default="*.json",
        alias="POKERGFX_FILE_PATTERN",
        description="Glob pattern for JSON files",
    )
    file_settle_delay: float = Field(
        default=0.5,
        description="Delay before reading file to ensure write completion",
    )

    # SMB Fallback settings (PRD-0010)
    fallback_enabled: bool = Field(
        default=True,
        alias="POKERGFX_FALLBACK_ENABLED",
        description="Enable local folder fallback when SMB fails",
    )
    fallback_path: str = Field(
        default="./data/manual_import",
        alias="POKERGFX_FALLBACK_PATH",
        description="Local fallback folder for manual file copy",
    )
    health_check_interval: float = Field(
        default=30.0,
        alias="POKERGFX_HEALTH_CHECK_INTERVAL",
        description="SMB health check interval in seconds",
    )
    max_reconnect_attempts: int = Field(
        default=5,
        alias="POKERGFX_MAX_RECONNECT",
        description="Maximum SMB reconnection attempts before fallback",
    )

    @model_validator(mode="after")
    def validate_json_mode_settings(self) -> "PokerGFXSettings":
        """Validate settings when json mode is selected.

        Raises:
            ValueError: If json_watch_path is not set in json mode
        """
        if self.mode == "json":
            if not self.json_watch_path:
                raise ValueError(
                    "POKERGFX_JSON_PATH must be set when using json mode. "
                    "See docs/NAS_SETUP.md for configuration guide."
                )
            # Check if path exists (warning only, not error)
            watch_path = Path(self.json_watch_path)
            if not watch_path.exists():
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Watch path does not exist: {self.json_watch_path}. "
                    f"Ensure NAS is mounted. See docs/NAS_SETUP.md for troubleshooting."
                )
        return self


class GeminiSettings(BaseSettings):
    """Gemini API configuration."""

    api_key: str = Field(default="", alias="GEMINI_API_KEY")
    model: str = Field(
        default="gemini-2.5-flash-native-audio-preview",
        alias="GEMINI_MODEL",
    )
    ws_url: str = Field(
        default="wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
    )
    session_timeout: int = Field(default=600, description="Session timeout in seconds (max 10min)")
    confidence_threshold: float = Field(
        default=0.80, description="Minimum confidence for secondary"
    )


class VideoSettings(BaseSettings):
    """Video capture configuration."""

    streams: list[str] = Field(default_factory=list, alias="VIDEO_STREAMS")
    fps: int = Field(default=1, alias="VIDEO_FPS", description="Frames per second to capture")
    jpeg_quality: int = Field(default=80, description="JPEG compression quality")
    buffer_size: int = Field(default=10, description="Frame buffer size")


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    host: str = Field(default="localhost", alias="DB_HOST")
    port: int = Field(default=5432, alias="DB_PORT")
    database: str = Field(default="poker_hands", alias="DB_NAME")
    username: str = Field(default="postgres", alias="DB_USER")
    password: str = Field(default="", alias="DB_PASSWORD")
    pool_size: int = Field(default=5, description="Connection pool size")


class VMixSettings(BaseSettings):
    """vMix API configuration."""

    host: str = Field(default="127.0.0.1", alias="VMIX_HOST")
    port: int = Field(default=8088, alias="VMIX_PORT")
    timeout: float = Field(default=5.0, description="API timeout in seconds")
    auto_record: bool = Field(default=True, alias="VMIX_AUTO_RECORD")


class RecordingSettings(BaseSettings):
    """Recording configuration."""

    output_path: str = Field(default="./recordings", alias="RECORDING_PATH")
    format: str = Field(default="mp4", description="Output format")
    max_duration_seconds: int = Field(default=600, description="Max recording duration")
    min_duration_seconds: int = Field(default=10, description="Min duration to save")


class GradingSettings(BaseSettings):
    """Hand grading configuration."""

    playtime_threshold: int = Field(
        default=120, description="Long playtime threshold in seconds"
    )
    board_combo_threshold: int = Field(
        default=7, description="Premium board combo rank threshold (1-7)"
    )


class FallbackSettings(BaseSettings):
    """Fallback/Plan B configuration."""

    enabled: bool = Field(default=True, alias="FALLBACK_ENABLED")
    primary_timeout: int = Field(
        default=30, description="Primary source timeout in seconds"
    )
    secondary_timeout: int = Field(
        default=60, description="Secondary source timeout in seconds"
    )
    mismatch_threshold: int = Field(
        default=3, description="Fusion mismatch count before fallback"
    )


class SupabaseSettings(BaseSettings):
    """Supabase configuration for NAS JSON sync."""

    url: str = Field(default="", alias="SUPABASE_URL")
    key: str = Field(default="", alias="SUPABASE_KEY")  # Service role key
    anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")

    # Retry settings
    max_retries: int = Field(default=3, description="Max retry attempts")
    retry_delay: float = Field(default=1.0, description="Initial retry delay in seconds")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")

    # Batch settings
    batch_size: int = Field(default=100, description="Batch insert size")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    pokergfx: PokerGFXSettings = Field(default_factory=PokerGFXSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)  # Deprecated
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)
    vmix: VMixSettings = Field(default_factory=VMixSettings)
    recording: RecordingSettings = Field(default_factory=RecordingSettings)
    grading: GradingSettings = Field(default_factory=GradingSettings)
    fallback: FallbackSettings = Field(default_factory=FallbackSettings)

    # General settings
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")

    # Table configuration
    table_ids: list[str] = Field(
        default_factory=lambda: ["table_1", "table_2", "table_3"],
        description="List of table identifiers",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
