"""Configuration for GFX JSON Simulator."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# 사용자 설정 파일 경로 (프로젝트 루트의 .simulator_settings.json)
USER_SETTINGS_FILE = Path(__file__).parents[2] / ".simulator_settings.json"


class SimulatorSettings(BaseSettings):
    """Settings for GFX JSON Simulator."""

    model_config = SettingsConfigDict(
        env_prefix="SIMULATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    source_path: Path = Field(
        default=Path("gfx_json"),
        description="Source directory containing GFX JSON files",
    )
    nas_path: Path = Field(
        default=Path("output"),
        description="Target NAS path for output files",
    )

    # Timing
    interval_sec: int = Field(
        default=60,
        ge=1,
        le=3600,  # Max 1 hour between hands
        description="Interval between hand generations in seconds (1-3600)",
    )

    # Retry settings
    retry_count: int = Field(
        default=3,
        ge=1,
        le=10,  # Max 10 retries
        description="Number of retries on NAS write failure (1-10)",
    )
    retry_delay_sec: int = Field(
        default=5,
        ge=1,
        le=60,  # Max 1 minute between retries
        description="Delay between retries in seconds (1-60)",
    )

    # Streamlit
    streamlit_port: int = Field(
        default=8501,
        ge=1024,
        le=65535,
        description="Streamlit server port (1024-65535)",
    )

    # History settings
    history_enabled: bool = Field(
        default=True,
        description="Enable processing history tracking",
    )
    warn_on_duplicate: bool = Field(
        default=True,
        description="Show warning when re-processing already processed files",
    )
    auto_resume_enabled: bool = Field(
        default=False,
        description="Automatically resume from last checkpoint on start",
    )

    @field_validator("source_path", "nas_path", mode="before")
    @classmethod
    def validate_path_not_empty(cls, v: Any) -> Path:
        """Validate that path is not empty."""
        if v is None:
            return Path(".")
        path = Path(v) if isinstance(v, str) else v
        if str(path).strip() == "":
            raise ValueError("Path cannot be empty")
        return path

    @model_validator(mode="after")
    def validate_paths_exist_warning(self) -> SimulatorSettings:
        """Log warning if paths don't exist (but don't fail).

        This is a soft validation - paths will be created on write.
        """
        if not self.source_path.exists():
            logger.warning(f"Source path does not exist: {self.source_path}")
        if not self.nas_path.exists():
            logger.debug(f"Target path does not exist (will be created): {self.nas_path}")
        return self


def get_simulator_settings() -> SimulatorSettings:
    """Get simulator settings instance."""
    return SimulatorSettings()


def load_user_settings() -> dict[str, Any]:
    """Load user settings from JSON file.

    Returns:
        Dictionary with saved settings, or empty dict if file doesn't exist.
    """
    if not USER_SETTINGS_FILE.exists():
        return {}

    try:
        data: dict[str, Any] = json.loads(
            USER_SETTINGS_FILE.read_text(encoding="utf-8")
        )
        logger.debug(f"Loaded user settings from {USER_SETTINGS_FILE}")
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load user settings: {e}")
        return {}


def save_user_settings(settings: dict[str, Any]) -> bool:
    """Save user settings to JSON file.

    Args:
        settings: Dictionary with settings to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        # 기존 설정 로드 후 병합
        existing = load_user_settings()
        existing.update(settings)

        USER_SETTINGS_FILE.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(f"Saved user settings to {USER_SETTINGS_FILE}")
        return True
    except OSError as e:
        logger.warning(f"Failed to save user settings: {e}")
        return False


def get_last_source_path() -> str | None:
    """Get last used source path."""
    settings = load_user_settings()
    return settings.get("last_source_path")


def get_last_target_path() -> str | None:
    """Get last used target path."""
    settings = load_user_settings()
    return settings.get("last_target_path")


def get_last_interval() -> int | None:
    """Get last used interval."""
    settings = load_user_settings()
    return settings.get("last_interval")


def save_paths(source_path: str | None = None, target_path: str | None = None) -> bool:
    """Save source and/or target paths.

    Args:
        source_path: Source directory path to save.
        target_path: Target directory path to save.

    Returns:
        True if saved successfully.
    """
    settings: dict[str, Any] = {}
    if source_path is not None:
        settings["last_source_path"] = source_path
    if target_path is not None:
        settings["last_target_path"] = target_path
    return save_user_settings(settings)


def save_interval(interval: int) -> bool:
    """Save interval setting.

    Args:
        interval: Interval in seconds.

    Returns:
        True if saved successfully.
    """
    return save_user_settings({"last_interval": interval})
