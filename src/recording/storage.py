"""Storage management for recording files."""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import RecordingSettings

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages storage for recording files.

    Handles file naming, organization, and post-recording file operations.
    """

    def __init__(self, settings: "RecordingSettings"):
        self.settings = settings
        self.base_path = Path(settings.output_path)

    def ensure_directories(self) -> None:
        """Ensure output directories exist."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Recording directory ensured: {self.base_path}")

    def get_table_directory(self, table_id: str) -> Path:
        """Get directory for a specific table."""
        table_dir = self.base_path / table_id
        table_dir.mkdir(parents=True, exist_ok=True)
        return table_dir

    def generate_filename(
        self,
        table_id: str,
        hand_number: int,
        timestamp: datetime | None = None,
        extension: str | None = None,
    ) -> str:
        """Generate standardized filename for a hand recording.

        Format: {table_id}_hand{hand_number}_{timestamp}.{extension}
        Example: table_1_hand42_20250125_143022.mp4
        """
        if timestamp is None:
            timestamp = datetime.now()

        ext = extension or self.settings.format
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")

        return f"{table_id}_hand{hand_number}_{ts_str}.{ext}"

    def get_full_path(
        self,
        table_id: str,
        hand_number: int,
        timestamp: datetime | None = None,
    ) -> Path:
        """Get full path for a recording file."""
        directory = self.get_table_directory(table_id)
        filename = self.generate_filename(table_id, hand_number, timestamp)
        return directory / filename

    def rename_recording(
        self,
        source_path: str,
        table_id: str,
        hand_number: int,
        timestamp: datetime | None = None,
    ) -> Path | None:
        """Rename a vMix recording to standardized format.

        vMix doesn't support dynamic filenames, so we rename after recording.

        Args:
            source_path: Original file path from vMix
            table_id: Table identifier
            hand_number: Hand number
            timestamp: Optional timestamp for filename

        Returns:
            New file path if successful, None otherwise
        """
        source = Path(source_path)
        if not source.exists():
            logger.error(f"Source file not found: {source_path}")
            return None

        # Get extension from source file
        extension = source.suffix.lstrip(".")

        target_dir = self.get_table_directory(table_id)
        target_filename = self.generate_filename(
            table_id, hand_number, timestamp, extension
        )
        target_path = target_dir / target_filename

        try:
            shutil.move(str(source), str(target_path))
            logger.info(f"Recording renamed: {source.name} -> {target_filename}")
            return target_path
        except Exception as e:
            logger.error(f"Failed to rename recording: {e}")
            return None

    def get_file_size(self, file_path: str) -> int | None:
        """Get file size in bytes."""
        try:
            return os.path.getsize(file_path)
        except OSError:
            return None

    def list_recordings(
        self,
        table_id: str | None = None,
        limit: int = 100,
    ) -> list[Path]:
        """List recording files.

        Args:
            table_id: Optional table filter
            limit: Maximum number of files to return

        Returns:
            List of file paths sorted by modification time (newest first)
        """
        if table_id:
            search_path = self.get_table_directory(table_id)
        else:
            search_path = self.base_path

        pattern = f"*.{self.settings.format}"
        files = list(search_path.glob(f"**/{pattern}"))

        # Sort by modification time (newest first)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        return files[:limit]

    def cleanup_old_recordings(
        self,
        max_age_days: int = 30,
        dry_run: bool = True,
    ) -> list[Path]:
        """Remove recordings older than specified days.

        Args:
            max_age_days: Maximum age in days
            dry_run: If True, only list files without deleting

        Returns:
            List of files deleted (or would be deleted in dry run)
        """
        import time

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        files_to_delete = []

        for file_path in self.list_recordings(limit=10000):
            if file_path.stat().st_mtime < cutoff_time:
                files_to_delete.append(file_path)
                if not dry_run:
                    try:
                        file_path.unlink()
                        logger.info(f"Deleted old recording: {file_path}")
                    except Exception as e:
                        logger.error(f"Failed to delete {file_path}: {e}")

        if dry_run:
            logger.info(
                f"Dry run: {len(files_to_delete)} files would be deleted "
                f"(older than {max_age_days} days)"
            )

        return files_to_delete

    def get_storage_stats(self) -> dict:
        """Get storage statistics."""
        total_size = 0
        file_count = 0
        tables = set()

        for file_path in self.list_recordings(limit=10000):
            total_size += file_path.stat().st_size
            file_count += 1
            # Extract table_id from path
            if file_path.parent != self.base_path:
                tables.add(file_path.parent.name)

        return {
            "base_path": str(self.base_path),
            "total_files": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "table_count": len(tables),
            "tables": list(tables),
        }
