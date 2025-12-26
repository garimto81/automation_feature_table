"""Application settings using pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PokerGFXSettings(BaseSettings):
    """PokerGFX API configuration."""

    api_url: str = Field(default="ws://localhost:8080", alias="POKERGFX_API_URL")
    api_key: str = Field(default="", alias="POKERGFX_API_KEY")
    reconnect_interval: int = Field(default=5, description="Reconnect interval in seconds")
    max_retries: int = Field(default=3, description="Maximum reconnection attempts")


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
    confidence_threshold: float = Field(default=0.80, description="Minimum confidence for secondary")


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
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
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
