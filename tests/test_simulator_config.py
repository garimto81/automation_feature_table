"""Tests for simulator config module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.simulator.config import (
    SimulatorSettings,
    get_last_interval,
    get_last_source_path,
    get_last_target_path,
    get_simulator_settings,
    load_user_settings,
    save_interval,
    save_paths,
    save_user_settings,
)


class TestSimulatorSettings:
    """Test cases for SimulatorSettings."""

    def test_default_values(self):
        """Test default settings values."""
        settings = SimulatorSettings()

        assert settings.source_path == Path("gfx_json")
        assert settings.nas_path == Path("output")
        assert settings.interval_sec == 60
        assert settings.retry_count == 3
        assert settings.retry_delay_sec == 5
        assert settings.streamlit_port == 8501
        assert settings.history_enabled is True
        assert settings.warn_on_duplicate is True
        assert settings.auto_resume_enabled is False

    def test_custom_values(self):
        """Test settings with custom values."""
        settings = SimulatorSettings(
            source_path=Path("custom/source"),
            nas_path=Path("custom/nas"),
            interval_sec=120,
            retry_count=5,
        )

        assert settings.source_path == Path("custom/source")
        assert settings.nas_path == Path("custom/nas")
        assert settings.interval_sec == 120
        assert settings.retry_count == 5

    def test_validate_interval_sec_min(self):
        """Test interval_sec minimum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(interval_sec=0)

    def test_validate_interval_sec_max(self):
        """Test interval_sec maximum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(interval_sec=3601)

    def test_validate_retry_count_min(self):
        """Test retry_count minimum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(retry_count=0)

    def test_validate_retry_count_max(self):
        """Test retry_count maximum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(retry_count=11)

    def test_validate_retry_delay_sec_min(self):
        """Test retry_delay_sec minimum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(retry_delay_sec=0)

    def test_validate_retry_delay_sec_max(self):
        """Test retry_delay_sec maximum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(retry_delay_sec=61)

    def test_validate_streamlit_port_min(self):
        """Test streamlit_port minimum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(streamlit_port=1023)

    def test_validate_streamlit_port_max(self):
        """Test streamlit_port maximum validation."""
        with pytest.raises(ValueError):
            SimulatorSettings(streamlit_port=65536)

    def test_validate_path_empty_string_source(self):
        """Test that empty source path string raises error."""
        with pytest.raises(ValueError, match="Path cannot be empty"):
            SimulatorSettings(source_path=" ")

    def test_validate_path_empty_string_nas(self):
        """Test that empty nas path string raises error."""
        with pytest.raises(ValueError, match="Path cannot be empty"):
            SimulatorSettings(nas_path=" ")

    def test_validate_path_none_becomes_current_dir(self):
        """Test that None path becomes current directory."""
        settings = SimulatorSettings(source_path=None, nas_path=None)
        assert settings.source_path == Path(".")
        assert settings.nas_path == Path(".")

    def test_validate_paths_exist_warning_logs(self):
        """Test that non-existent paths log warnings."""
        with patch("src.simulator.config.logger") as mock_logger:
            SimulatorSettings(
                source_path=Path("nonexistent/source"),
                nas_path=Path("nonexistent/nas"),
            )

            # Should log warning for source path
            assert any(
                "Source path does not exist" in str(call)
                for call in mock_logger.warning.call_args_list
            )

            # Should log debug for target path
            assert any(
                "Target path does not exist" in str(call)
                for call in mock_logger.debug.call_args_list
            )


class TestGetSimulatorSettings:
    """Test cases for get_simulator_settings."""

    def test_get_simulator_settings(self):
        """Test getting simulator settings instance."""
        settings = get_simulator_settings()
        assert isinstance(settings, SimulatorSettings)


class TestUserSettings:
    """Test cases for user settings persistence."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_settings_file = Path("test_simulator_settings.json")

    def teardown_method(self):
        """Clean up test files."""
        if self.test_settings_file.exists():
            self.test_settings_file.unlink()

    def test_load_user_settings_file_not_exists(self):
        """Test loading settings when file doesn't exist."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            settings = load_user_settings()
            assert settings == {}

    def test_load_user_settings_success(self):
        """Test loading settings successfully."""
        test_data = {"last_source_path": "/path/to/source", "last_interval": 120}
        self.test_settings_file.write_text(json.dumps(test_data), encoding="utf-8")

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            settings = load_user_settings()
            assert settings == test_data

    def test_load_user_settings_invalid_json(self):
        """Test loading settings with invalid JSON."""
        self.test_settings_file.write_text("invalid json", encoding="utf-8")

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            with patch("src.simulator.config.logger") as mock_logger:
                settings = load_user_settings()
                assert settings == {}
                mock_logger.warning.assert_called_once()

    def test_save_user_settings_success(self):
        """Test saving user settings successfully."""
        test_data = {"last_source_path": "/path/to/source"}

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_user_settings(test_data)
            assert result is True

            # Verify saved data
            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == test_data

    def test_save_user_settings_merges_existing(self):
        """Test that save merges with existing settings."""
        existing_data = {"key1": "value1"}
        self.test_settings_file.write_text(
            json.dumps(existing_data), encoding="utf-8"
        )

        new_data = {"key2": "value2"}

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_user_settings(new_data)
            assert result is True

            # Verify merged data
            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == {"key1": "value1", "key2": "value2"}

    def test_save_user_settings_os_error(self):
        """Test saving settings with OS error."""
        with patch(
            "src.simulator.config.USER_SETTINGS_FILE", Path("/invalid/path/file.json")
        ):
            with patch("src.simulator.config.logger") as mock_logger:
                result = save_user_settings({"key": "value"})
                assert result is False
                mock_logger.warning.assert_called_once()


class TestGetLastSettings:
    """Test cases for get_last_* functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_settings_file = Path("test_simulator_settings.json")

    def teardown_method(self):
        """Clean up test files."""
        if self.test_settings_file.exists():
            self.test_settings_file.unlink()

    def test_get_last_source_path_exists(self):
        """Test getting last source path when it exists."""
        test_data = {"last_source_path": "/path/to/source"}
        self.test_settings_file.write_text(json.dumps(test_data), encoding="utf-8")

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = get_last_source_path()
            assert result == "/path/to/source"

    def test_get_last_source_path_not_exists(self):
        """Test getting last source path when it doesn't exist."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = get_last_source_path()
            assert result is None

    def test_get_last_target_path_exists(self):
        """Test getting last target path when it exists."""
        test_data = {"last_target_path": "/path/to/target"}
        self.test_settings_file.write_text(json.dumps(test_data), encoding="utf-8")

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = get_last_target_path()
            assert result == "/path/to/target"

    def test_get_last_target_path_not_exists(self):
        """Test getting last target path when it doesn't exist."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = get_last_target_path()
            assert result is None

    def test_get_last_interval_exists(self):
        """Test getting last interval when it exists."""
        test_data = {"last_interval": 120}
        self.test_settings_file.write_text(json.dumps(test_data), encoding="utf-8")

        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = get_last_interval()
            assert result == 120

    def test_get_last_interval_not_exists(self):
        """Test getting last interval when it doesn't exist."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = get_last_interval()
            assert result is None


class TestSavePaths:
    """Test cases for save_paths function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_settings_file = Path("test_simulator_settings.json")

    def teardown_method(self):
        """Clean up test files."""
        if self.test_settings_file.exists():
            self.test_settings_file.unlink()

    def test_save_paths_source_only(self):
        """Test saving only source path."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_paths(source_path="/path/to/source")
            assert result is True

            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == {"last_source_path": "/path/to/source"}

    def test_save_paths_target_only(self):
        """Test saving only target path."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_paths(target_path="/path/to/target")
            assert result is True

            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == {"last_target_path": "/path/to/target"}

    def test_save_paths_both(self):
        """Test saving both paths."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_paths(
                source_path="/path/to/source", target_path="/path/to/target"
            )
            assert result is True

            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == {
                "last_source_path": "/path/to/source",
                "last_target_path": "/path/to/target",
            }

    def test_save_paths_none(self):
        """Test saving with both paths None."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_paths(source_path=None, target_path=None)
            assert result is True

            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == {}


class TestSaveInterval:
    """Test cases for save_interval function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_settings_file = Path("test_simulator_settings.json")

    def teardown_method(self):
        """Clean up test files."""
        if self.test_settings_file.exists():
            self.test_settings_file.unlink()

    def test_save_interval_success(self):
        """Test saving interval successfully."""
        with patch("src.simulator.config.USER_SETTINGS_FILE", self.test_settings_file):
            result = save_interval(120)
            assert result is True

            saved_data = json.loads(self.test_settings_file.read_text(encoding="utf-8"))
            assert saved_data == {"last_interval": 120}
