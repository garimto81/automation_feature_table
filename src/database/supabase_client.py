"""Supabase client management with retry logic."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from supabase import Client, create_client

if TYPE_CHECKING:
    from src.config.settings import SupabaseSettings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SupabaseError(Exception):
    """Base exception for Supabase operations."""

    pass


class DuplicateSessionError(SupabaseError):
    """Raised when attempting to insert duplicate session."""

    pass


class SyncFailedError(SupabaseError):
    """Raised when file sync fails after all retries."""

    pass


class SupabaseManager:
    """Manages Supabase client connections with retry logic.

    Usage:
        manager = SupabaseManager(settings)
        result = await manager.execute_with_retry(
            lambda: manager.client.table("gfx_sessions").select("*").execute()
        )
    """

    def __init__(self, settings: SupabaseSettings) -> None:
        """Initialize Supabase manager.

        Args:
            settings: Supabase configuration settings
        """
        self.settings = settings
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        """Get or create Supabase client.

        Returns:
            Supabase client instance
        """
        if self._client is None:
            if not self.settings.url or not self.settings.key:
                raise SupabaseError(
                    "Supabase URL and KEY must be configured. "
                    "Set SUPABASE_URL and SUPABASE_KEY environment variables."
                )

            self._client = create_client(
                self.settings.url,
                self.settings.key,
            )
            logger.info(f"Supabase client created for {self.settings.url}")

        return self._client

    async def execute_with_retry(
        self,
        operation: Callable[[], T],
    ) -> T:
        """Execute operation with exponential backoff retry.

        Args:
            operation: Callable that performs the Supabase operation

        Returns:
            Result of the operation

        Raises:
            DuplicateSessionError: If duplicate key violation detected
            SyncFailedError: If all retries exhausted
        """
        last_error: Exception | None = None
        delay = self.settings.retry_delay

        for attempt in range(self.settings.max_retries):
            try:
                result = operation()
                return result
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Don't retry on duplicate errors
                if "duplicate" in error_str or "unique" in error_str:
                    raise DuplicateSessionError(str(e)) from e

                logger.warning(
                    f"Supabase operation failed "
                    f"(attempt {attempt + 1}/{self.settings.max_retries}): {e}"
                )

                if attempt < self.settings.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff

        raise SyncFailedError(
            f"Operation failed after {self.settings.max_retries} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def compute_file_hash(content: bytes) -> str:
        """Compute SHA256 hash for file content.

        Args:
            content: File content as bytes

        Returns:
            Hexadecimal SHA256 hash string
        """
        return hashlib.sha256(content).hexdigest()

    async def health_check(self) -> bool:
        """Check Supabase connection health.

        Returns:
            True if connection is healthy
        """
        try:
            self.client.table("gfx_sessions").select("id").limit(1).execute()
            logger.debug("Supabase health check passed")
            return True
        except Exception as e:
            logger.error(f"Supabase health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close client connection."""
        self._client = None
        logger.info("Supabase client closed")

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics.

        Returns:
            Dictionary with connection stats
        """
        return {
            "url": self.settings.url,
            "connected": self._client is not None,
            "max_retries": self.settings.max_retries,
            "timeout": self.settings.timeout,
        }
