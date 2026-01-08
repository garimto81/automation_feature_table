"""Configuration for GFX JSON Simulator."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        description="Interval between hand generations in seconds",
    )

    # Retry settings
    retry_count: int = Field(
        default=3,
        ge=1,
        description="Number of retries on NAS write failure",
    )
    retry_delay_sec: int = Field(
        default=5,
        ge=1,
        description="Delay between retries in seconds",
    )

    # Streamlit
    streamlit_port: int = Field(
        default=8501,
        description="Streamlit server port",
    )


def get_simulator_settings() -> SimulatorSettings:
    """Get simulator settings instance."""
    return SimulatorSettings()
