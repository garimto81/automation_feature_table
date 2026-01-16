"""Extended tests for JSON file watcher - targeting 70%+ coverage."""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.hand import HandRank
from src.primary.json_file_watcher import (
    FileEvent,
    JSONFileHandler,
    JSONFileWatcher,
    SupabaseJSONFileWatcher,
)


class TestJSONFileWatcherFileReady:
    """Test _wait_for_file_ready method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock PokerGFX settings."""
        settings = MagicMock()
        settings.json_watch_path = ""
        settings.file_settle_delay = 0.05
        settings.processed_db_path = ""
        settings.file_pattern = "*.json"
        return settings

    async def test_wait_for_file_ready_stable_size(
        self, mock_settings, tmp_path: Path
    ):
        """Test file ready check with stable size."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"test": "data"}')

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        result = await watcher._wait_for_file_ready(test_file)

        assert result is True

    async def test_wait_for_file_ready_file_disappeared(
        self, mock_settings, tmp_path: Path
    ):
        """Test file ready check when file disappears."""
        test_file = tmp_path / "missing.json"

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        result = await watcher._wait_for_file_ready(test_file)

        assert result is False

    async def test_wait_for_file_ready_max_retries_exceeded(
        self, mock_settings, tmp_path: Path
    ):
        """Test file ready check when max retries exceeded."""
        test_file = tmp_path / "changing.json"

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")
        mock_settings.file_settle_delay = 0.01

        watcher = JSONFileWatcher(mock_settings)

        # File doesn't exist - will fail all retries
        result = await watcher._wait_for_file_ready(test_file, max_retries=2)

        assert result is False


class TestJSONFileWatcherMoveError:
    """Test _move_to_error_folder method."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.json_watch_path = ""
        settings.file_settle_delay = 0.05
        settings.processed_db_path = ""
        settings.file_pattern = "*.json"
        return settings

    async def test_move_to_error_folder_success(
        self, mock_settings, tmp_path: Path
    ):
        """Test moving corrupted file to error folder."""
        test_file = tmp_path / "corrupted.json"
        test_file.write_text("invalid json")

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        await watcher._move_to_error_folder(test_file)

        error_dir = tmp_path / "errors"
        assert error_dir.exists()
        assert len(list(error_dir.glob("*corrupted.json"))) == 1

    async def test_move_to_error_folder_os_error(
        self, mock_settings, tmp_path: Path
    ):
        """Test error handling when move fails."""
        test_file = tmp_path / "test.json"
        test_file.write_text("data")

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)

        # Mock rename to raise OSError
        with patch.object(Path, "rename", side_effect=OSError("Move failed")):
            # Should not raise, just log error
            await watcher._move_to_error_folder(test_file)


class TestJSONFileWatcherListen:
    """Test listen method with various scenarios."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.json_watch_path = ""
        settings.polling_interval = 0.1
        settings.file_settle_delay = 0.05
        settings.processed_db_path = ""
        settings.file_pattern = "*.json"
        settings.max_reconnect_attempts = 3
        return settings

    async def test_listen_nas_connection_fail(self, mock_settings, tmp_path: Path):
        """Test listen raises RuntimeError when NAS check fails."""
        mock_settings.json_watch_path = "/nonexistent/path"
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)

        with pytest.raises(RuntimeError, match="Cannot access watch path"):
            async for _ in watcher.listen():
                pass

    async def test_listen_with_timeout_and_reconnect(
        self, mock_settings, tmp_path: Path
    ):
        """Test listen with timeout and reconnect logic."""
        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)

        # Mock _check_nas_connection to fail then succeed
        check_count = 0

        async def mock_check_nas():
            nonlocal check_count
            check_count += 1
            return check_count <= 1 or check_count > 2

        with patch.object(watcher, "_check_nas_connection", side_effect=mock_check_nas):
            # Run for short time then stop
            results = []
            watcher._running = True

            async def stop_after_delay():
                await asyncio.sleep(0.5)
                watcher._running = False

            stop_task = asyncio.create_task(stop_after_delay())

            try:
                async for result in watcher.listen():
                    results.append(result)
            except Exception:
                pass
            finally:
                await stop_task

            # Should have attempted reconnection
            assert check_count >= 2


class TestJSONFileWatcherDisconnect:
    """Test disconnect/stop methods."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.json_watch_path = ""
        settings.file_settle_delay = 0.05
        settings.processed_db_path = ""
        settings.file_pattern = "*.json"
        return settings

    async def test_disconnect_alias(self, mock_settings, tmp_path: Path):
        """Test disconnect is an alias for stop."""
        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        watcher._running = True

        await watcher.disconnect()

        assert watcher._running is False

    async def test_stop_without_observer(self, mock_settings, tmp_path: Path):
        """Test stop when observer is None."""
        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.processed_db_path = str(tmp_path / "processed.json")

        watcher = JSONFileWatcher(mock_settings)
        watcher._running = True
        watcher._observer = None

        await watcher.stop()

        assert watcher._running is False


class TestSupabaseJSONFileWatcher:
    """Test SupabaseJSONFileWatcher class."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.json_watch_path = ""
        settings.polling_interval = 0.1
        settings.file_settle_delay = 0.05
        settings.file_pattern = "*.json"
        return settings

    @pytest.fixture
    def mock_supabase(self):
        """Create mock Supabase manager."""
        manager = AsyncMock()
        manager.health_check = AsyncMock(return_value=True)
        return manager

    @pytest.fixture
    def mock_session_repo(self):
        """Create mock session repository."""
        repo = AsyncMock()
        repo.save_session = AsyncMock(return_value={"id": 1})
        repo.get_by_session_id = AsyncMock(return_value=None)
        repo.update_session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_sync_log_repo(self):
        """Create mock sync log repository."""
        repo = AsyncMock()
        repo.is_file_processed = AsyncMock(return_value=False)
        repo.log_sync_start = AsyncMock(return_value={"id": 1})
        repo.log_sync_complete = AsyncMock()
        return repo

    @pytest.fixture
    def mock_hands_repo(self):
        """Create mock hands repository."""
        repo = AsyncMock()
        repo.save_hands = AsyncMock()
        repo.get_new_hands = AsyncMock(return_value=[])
        return repo

    def test_supabase_watcher_init(
        self, mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
    ):
        """Test SupabaseJSONFileWatcher initialization."""
        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        assert watcher.settings == mock_settings
        assert watcher.supabase == mock_supabase
        assert watcher._running is False

    async def test_compute_file_hash(
        self,
        mock_settings,
        mock_supabase,
        mock_session_repo,
        mock_sync_log_repo,
        tmp_path: Path,
    ):
        """Test file hash computation."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"test": "data"}')

        mock_settings.json_watch_path = str(tmp_path)

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        file_hash = await watcher._compute_file_hash(test_file)

        assert isinstance(file_hash, str)
        assert len(file_hash) == 64  # SHA256 hex length

    async def test_check_nas_connection_fail(
        self, mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
    ):
        """Test NAS connection check failure."""
        mock_settings.json_watch_path = "/nonexistent"

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        result = await watcher._check_nas_connection()

        assert result is False

    async def test_process_file_already_processed(
        self,
        mock_settings,
        mock_supabase,
        mock_session_repo,
        mock_sync_log_repo,
        tmp_path: Path,
    ):
        """Test processing already processed file."""
        test_file = tmp_path / "test.json"
        test_data = {"ID": 123, "Hands": []}
        test_file.write_text(json.dumps(test_data))

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.file_settle_delay = 0.01

        # Mark as already processed
        mock_sync_log_repo.is_file_processed = AsyncMock(return_value=True)

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        results = await watcher._process_file(str(test_file))

        assert len(results) == 0

    async def test_process_file_duplicate_session(
        self,
        mock_settings,
        mock_supabase,
        mock_session_repo,
        mock_sync_log_repo,
        tmp_path: Path,
    ):
        """Test processing file with duplicate session."""
        test_file = tmp_path / "test.json"
        test_data = {"ID": 123, "Hands": []}
        test_file.write_text(json.dumps(test_data))

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.file_settle_delay = 0.01

        # Return None for duplicate
        mock_session_repo.save_session = AsyncMock(return_value=None)

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        results = await watcher._process_file(str(test_file))

        assert len(results) == 0

    async def test_process_file_exception_handling(
        self,
        mock_settings,
        mock_supabase,
        mock_session_repo,
        mock_sync_log_repo,
        tmp_path: Path,
    ):
        """Test processing file with generic exception."""
        test_file = tmp_path / "test.json"
        test_data = {"ID": 123, "Hands": []}
        test_file.write_text(json.dumps(test_data))

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.file_settle_delay = 0.01

        # Mock save_session to raise exception
        mock_session_repo.save_session = AsyncMock(side_effect=Exception("DB error"))

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        results = await watcher._process_file(str(test_file))

        assert len(results) == 0

    async def test_handle_modified_file_no_existing_session(
        self,
        mock_settings,
        mock_supabase,
        mock_session_repo,
        mock_sync_log_repo,
        mock_hands_repo,
        tmp_path: Path,
    ):
        """Test modified file with no existing session."""
        test_file = tmp_path / "test.json"
        test_data = {
            "ID": 123,
            "Hands": [{"HandNum": 1, "Players": [], "Events": []}],
        }
        test_file.write_text(json.dumps(test_data))

        mock_settings.json_watch_path = str(tmp_path)
        mock_settings.file_settle_delay = 0.01

        # No existing session
        mock_session_repo.get_by_session_id = AsyncMock(return_value=None)

        watcher = SupabaseJSONFileWatcher(
            mock_settings,
            mock_supabase,
            mock_session_repo,
            mock_sync_log_repo,
            mock_hands_repo,
        )

        # Should recursively call with "created"
        with patch.object(
            watcher, "_process_file", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = []
            await watcher._handle_modified_file(
                test_file,
                "test.json",
                "hash123",
                test_data,
                123,
                test_data["Hands"],
            )

            # Should call _process_file with "created"
            mock_process.assert_called_once()

    async def test_listen_supabase_health_fail(
        self,
        mock_settings,
        mock_supabase,
        mock_session_repo,
        mock_sync_log_repo,
        tmp_path: Path,
    ):
        """Test listen raises error when Supabase health check fails."""
        mock_settings.json_watch_path = str(tmp_path)

        # Fail health check
        mock_supabase.health_check = AsyncMock(return_value=False)

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        with pytest.raises(RuntimeError, match="Supabase connection failed"):
            async for _ in watcher.listen():
                pass

    async def test_get_stats(
        self, mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
    ):
        """Test statistics retrieval."""
        mock_settings.json_watch_path = "/test/path"
        mock_settings.polling_interval = 2.0

        watcher = SupabaseJSONFileWatcher(
            mock_settings, mock_supabase, mock_session_repo, mock_sync_log_repo
        )

        stats = watcher.get_stats()

        assert stats["watch_path"] == "/test/path"
        assert stats["polling_interval"] == 2.0
        assert stats["backend"] == "supabase"
        assert stats["is_running"] is False
