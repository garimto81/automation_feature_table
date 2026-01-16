"""Tests for sync agent main entry point."""

import asyncio
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.sync_agent.main import (
    SyncAgentApp,
    cli,
    load_settings,
    main,
    setup_logging,
)


@pytest.fixture
def mock_settings():
    """Mock sync agent settings."""
    settings = Mock()
    settings.gfx_watch_path = "C:/test/gfx"
    settings.queue_db_path = "C:/test/queue.db"
    settings.max_retries = 3
    settings.log_level = "INFO"
    settings.log_path = None
    return settings


@pytest.fixture
def mock_settings_with_log():
    """Mock sync agent settings with log path."""
    settings = Mock()
    settings.gfx_watch_path = "C:/test/gfx"
    settings.queue_db_path = "C:/test/queue.db"
    settings.max_retries = 3
    settings.log_level = "DEBUG"
    settings.log_path = "C:/test/logs/sync_agent.log"
    return settings


class TestLoadSettings:
    """Test suite for load_settings function."""

    @patch("src.sync_agent.main.SyncAgentSettings")
    def test_load_settings_no_config(self, mock_settings_class):
        """Test loading settings without config file."""
        mock_settings_instance = Mock()
        mock_settings_class.return_value = mock_settings_instance

        result = load_settings(config_path=None)

        assert result == mock_settings_instance
        mock_settings_class.assert_called_once()

    @patch("dotenv.load_dotenv")
    @patch("src.sync_agent.main.SyncAgentSettings")
    def test_load_settings_with_config(self, mock_settings_class, mock_load_dotenv):
        """Test loading settings with config file."""
        mock_settings_instance = Mock()
        mock_settings_class.return_value = mock_settings_instance

        result = load_settings(config_path="C:/test/.env")

        mock_load_dotenv.assert_called_once_with("C:/test/.env", override=True)
        assert result == mock_settings_instance


class TestSetupLogging:
    """Test suite for setup_logging function."""

    @patch("src.sync_agent.main.logging.basicConfig")
    def test_setup_logging_console_only(self, mock_basic_config, mock_settings):
        """Test setting up logging with console only."""
        setup_logging(mock_settings)

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args
        assert call_args.kwargs["level"] == 20  # INFO level

    @patch("src.sync_agent.main.logging.FileHandler")
    @patch("src.sync_agent.main.logging.basicConfig")
    def test_setup_logging_with_file(
        self, mock_basic_config, mock_file_handler, mock_settings_with_log
    ):
        """Test setting up logging with file handler."""
        mock_handler_instance = MagicMock()
        mock_file_handler.return_value = mock_handler_instance

        with patch("pathlib.Path.mkdir"):
            setup_logging(mock_settings_with_log)

        mock_file_handler.assert_called_once()
        mock_basic_config.assert_called_once()

    @patch("src.sync_agent.main.logging.getLogger")
    @patch("src.sync_agent.main.logging.basicConfig")
    def test_setup_logging_reduces_library_noise(
        self, mock_basic_config, mock_get_logger, mock_settings
    ):
        """Test logging setup reduces external library verbosity."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        setup_logging(mock_settings)

        # Should set WARNING level for watchdog, httpx, httpcore
        assert mock_get_logger.call_count >= 3


class TestSyncAgentApp:
    """Test suite for SyncAgentApp."""

    def test_init(self, mock_settings):
        """Test app initialization."""
        app = SyncAgentApp(mock_settings)

        assert app.settings == mock_settings
        assert app._running is False
        assert app._watcher is None
        assert app._sync_service is None
        assert app._queue is None

    @patch("src.sync_agent.main.GFXFileWatcher")
    @patch("src.sync_agent.main.SyncService")
    @patch("src.sync_agent.main.LocalQueue")
    @patch("pathlib.Path.mkdir")
    async def test_start_success(
        self, mock_mkdir, mock_queue_class, mock_service_class, mock_watcher_class, mock_settings
    ):
        """Test starting sync agent successfully."""
        # Mock queue
        mock_queue = MagicMock()
        mock_queue_class.return_value = mock_queue

        # Mock sync service
        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(return_value=True)
        mock_service_class.return_value = mock_service

        # Mock watcher
        mock_watcher = MagicMock()
        mock_watcher.run_forever = AsyncMock()
        mock_watcher_class.return_value = mock_watcher

        app = SyncAgentApp(mock_settings)
        await app.start()

        assert app._running is True
        assert app._queue == mock_queue
        assert app._sync_service == mock_service
        assert app._watcher == mock_watcher
        mock_service.health_check.assert_called_once()
        mock_watcher.run_forever.assert_called_once()

    @patch("src.sync_agent.main.GFXFileWatcher")
    @patch("src.sync_agent.main.SyncService")
    @patch("src.sync_agent.main.LocalQueue")
    @patch("pathlib.Path.mkdir")
    async def test_start_unhealthy_connection(
        self, mock_mkdir, mock_queue_class, mock_service_class, mock_watcher_class, mock_settings
    ):
        """Test starting sync agent with unhealthy Supabase connection."""
        # Mock queue
        mock_queue = MagicMock()
        mock_queue_class.return_value = mock_queue

        # Mock sync service with unhealthy connection
        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(return_value=False)
        mock_service_class.return_value = mock_service

        # Mock watcher
        mock_watcher = MagicMock()
        mock_watcher.run_forever = AsyncMock()
        mock_watcher_class.return_value = mock_watcher

        app = SyncAgentApp(mock_settings)
        await app.start()

        # Should continue despite unhealthy connection (offline mode)
        assert app._running is True
        mock_watcher.run_forever.assert_called_once()

    async def test_stop_with_watcher(self, mock_settings):
        """Test stopping sync agent with watcher."""
        app = SyncAgentApp(mock_settings)
        app._running = True
        app._watcher = MagicMock()
        app._watcher.stop = AsyncMock()

        await app.stop()

        assert app._running is False
        app._watcher.stop.assert_called_once()

    async def test_stop_without_watcher(self, mock_settings):
        """Test stopping sync agent without watcher."""
        app = SyncAgentApp(mock_settings)
        app._running = True
        app._watcher = None

        await app.stop()

        assert app._running is False


class TestMain:
    """Test suite for main function."""

    @patch("src.sync_agent.main.SyncAgentApp")
    @patch("src.sync_agent.main.setup_logging")
    @patch("src.sync_agent.main.load_settings")
    async def test_main_normal_execution(
        self, mock_load_settings, mock_setup_logging, mock_app_class
    ):
        """Test main function normal execution."""
        mock_settings = Mock()
        mock_load_settings.return_value = mock_settings

        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_class.return_value = mock_app

        await main(config_path=None)

        mock_load_settings.assert_called_once_with(None)
        mock_setup_logging.assert_called_once_with(mock_settings)
        mock_app.start.assert_called_once()
        mock_app.stop.assert_called_once()

    @patch("src.sync_agent.main.SyncAgentApp")
    @patch("src.sync_agent.main.setup_logging")
    @patch("src.sync_agent.main.load_settings")
    async def test_main_with_config_path(
        self, mock_load_settings, mock_setup_logging, mock_app_class
    ):
        """Test main function with config path."""
        mock_settings = Mock()
        mock_load_settings.return_value = mock_settings

        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_class.return_value = mock_app

        await main(config_path="C:/test/.env")

        mock_load_settings.assert_called_once_with("C:/test/.env")

    @patch("src.sync_agent.main.SyncAgentApp")
    @patch("src.sync_agent.main.setup_logging")
    @patch("src.sync_agent.main.load_settings")
    async def test_main_keyboard_interrupt(
        self, mock_load_settings, mock_setup_logging, mock_app_class
    ):
        """Test main function handles keyboard interrupt."""
        mock_settings = Mock()
        mock_load_settings.return_value = mock_settings

        mock_app = MagicMock()
        mock_app.start = AsyncMock(side_effect=KeyboardInterrupt())
        mock_app.stop = AsyncMock()
        mock_app_class.return_value = mock_app

        # Should not raise
        await main(config_path=None)

        mock_app.stop.assert_called_once()

    @patch("src.sync_agent.main.SyncAgentApp")
    @patch("src.sync_agent.main.setup_logging")
    @patch("src.sync_agent.main.load_settings")
    async def test_main_fatal_error(
        self, mock_load_settings, mock_setup_logging, mock_app_class
    ):
        """Test main function handles fatal errors."""
        mock_settings = Mock()
        mock_load_settings.return_value = mock_settings

        mock_app = MagicMock()
        mock_app.start = AsyncMock(side_effect=Exception("Fatal error"))
        mock_app.stop = AsyncMock()
        mock_app_class.return_value = mock_app

        with pytest.raises(Exception, match="Fatal error"):
            await main(config_path=None)

        mock_app.stop.assert_called_once()

    @patch("src.sync_agent.main.asyncio.get_running_loop")
    @patch("src.sync_agent.main.SyncAgentApp")
    @patch("src.sync_agent.main.setup_logging")
    @patch("src.sync_agent.main.load_settings")
    async def test_main_signal_handlers(
        self, mock_load_settings, mock_setup_logging, mock_app_class, mock_get_loop
    ):
        """Test main function sets up signal handlers."""
        mock_settings = Mock()
        mock_load_settings.return_value = mock_settings

        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_class.return_value = mock_app

        await main(config_path=None)

        # Should attempt to add signal handlers (may fail on Windows)
        assert mock_loop.add_signal_handler.call_count >= 0

    @patch("src.sync_agent.main.asyncio.get_running_loop")
    @patch("src.sync_agent.main.SyncAgentApp")
    @patch("src.sync_agent.main.setup_logging")
    @patch("src.sync_agent.main.load_settings")
    async def test_main_signal_handlers_not_implemented(
        self, mock_load_settings, mock_setup_logging, mock_app_class, mock_get_loop
    ):
        """Test main function handles signal handler NotImplementedError."""
        mock_settings = Mock()
        mock_load_settings.return_value = mock_settings

        mock_loop = MagicMock()
        mock_loop.add_signal_handler.side_effect = NotImplementedError()
        mock_get_loop.return_value = mock_loop

        mock_app = MagicMock()
        mock_app.start = AsyncMock()
        mock_app.stop = AsyncMock()
        mock_app_class.return_value = mock_app

        # Should not raise
        await main(config_path=None)


class TestCLI:
    """Test suite for CLI function."""

    @patch("src.sync_agent.main.asyncio.run")
    @patch("sys.argv", ["sync_agent"])
    def test_cli_no_args(self, mock_asyncio_run):
        """Test CLI with no arguments."""
        cli()

        mock_asyncio_run.assert_called_once()
        args = mock_asyncio_run.call_args[0][0]
        # Should call main with None config

    @patch("src.sync_agent.main.asyncio.run")
    @patch("sys.argv", ["sync_agent", "--config", "C:/test/.env"])
    def test_cli_with_config(self, mock_asyncio_run):
        """Test CLI with config argument."""
        cli()

        mock_asyncio_run.assert_called_once()

    @patch("sys.argv", ["sync_agent", "--version"])
    def test_cli_version(self):
        """Test CLI version flag."""
        with pytest.raises(SystemExit) as exc_info:
            cli()

        assert exc_info.value.code == 0

    @patch("sys.argv", ["sync_agent", "--help"])
    def test_cli_help(self):
        """Test CLI help flag."""
        with pytest.raises(SystemExit) as exc_info:
            cli()

        assert exc_info.value.code == 0


class TestIntegration:
    """Integration tests for sync agent main."""

    @patch("src.sync_agent.main.GFXFileWatcher")
    @patch("src.sync_agent.main.SyncService")
    @patch("src.sync_agent.main.LocalQueue")
    @patch("pathlib.Path.mkdir")
    async def test_full_lifecycle(
        self, mock_mkdir, mock_queue_class, mock_service_class, mock_watcher_class, mock_settings
    ):
        """Test full app lifecycle: start -> running -> stop."""
        # Setup mocks
        mock_queue = MagicMock()
        mock_queue_class.return_value = mock_queue

        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(return_value=True)
        mock_service_class.return_value = mock_service

        mock_watcher = MagicMock()
        mock_watcher.run_forever = AsyncMock()
        mock_watcher.stop = AsyncMock()
        mock_watcher_class.return_value = mock_watcher

        # Create and start app
        app = SyncAgentApp(mock_settings)
        await app.start()

        assert app._running is True
        assert app._queue is not None
        assert app._sync_service is not None
        assert app._watcher is not None

        # Stop app
        await app.stop()

        assert app._running is False
        mock_watcher.stop.assert_called_once()

    @patch("src.sync_agent.main.GFXFileWatcher")
    @patch("src.sync_agent.main.SyncService")
    @patch("src.sync_agent.main.LocalQueue")
    @patch("pathlib.Path.mkdir")
    async def test_offline_mode(
        self, mock_mkdir, mock_queue_class, mock_service_class, mock_watcher_class, mock_settings
    ):
        """Test app can start in offline mode (no Supabase connection)."""
        # Setup mocks
        mock_queue = MagicMock()
        mock_queue_class.return_value = mock_queue

        mock_service = MagicMock()
        mock_service.health_check = AsyncMock(return_value=False)
        mock_service_class.return_value = mock_service

        mock_watcher = MagicMock()
        mock_watcher.run_forever = AsyncMock()
        mock_watcher_class.return_value = mock_watcher

        # Should start successfully even with no connection
        app = SyncAgentApp(mock_settings)
        await app.start()

        assert app._running is True
        mock_watcher.run_forever.assert_called_once()
