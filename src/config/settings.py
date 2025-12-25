"""Application settings using pydantic-settings."""

from functools import lru_cache
from typing import Optional

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


class Hand2NoteSettings(BaseSettings):
    """Hand2Note integration configuration."""

    enabled: bool = Field(default=True, alias="HAND2NOTE_ENABLED")
    dll_path: Optional[str] = Field(default=None, description="Path to Hand2Note API DLL")


class OutputSettings(BaseSettings):
    """Output configuration."""

    overlay_ws_port: int = Field(default=8081, alias="OVERLAY_WS_PORT")
    clip_markers_path: str = Field(default="./output/markers", alias="CLIP_MARKERS_PATH")
    edl_format: str = Field(default="cmx3600", description="EDL format: cmx3600, fcpxml")


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
    hand2note: Hand2NoteSettings = Field(default_factory=Hand2NoteSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)

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
