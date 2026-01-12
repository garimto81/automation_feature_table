"""Repository classes for Supabase database operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from src.database.supabase_client import DuplicateSessionError

if TYPE_CHECKING:
    from src.database.supabase_client import SupabaseManager

logger = logging.getLogger(__name__)


class GFXSessionRepository:
    """Repository for GFX session operations.

    Handles raw JSON session storage and duplicate detection.
    """

    def __init__(self, supabase: SupabaseManager) -> None:
        """Initialize repository.

        Args:
            supabase: Supabase manager instance
        """
        self.supabase = supabase

    async def save_session(
        self,
        session_id: int,
        file_name: str,
        file_hash: str,
        raw_json: dict[str, Any],
        nas_path: str | None = None,
    ) -> dict[str, Any] | None:
        """Save raw GFX session JSON to Supabase.

        Args:
            session_id: PokerGFX session ID (Windows FileTime)
            file_name: Original file name
            file_hash: SHA256 hash of file content
            raw_json: Complete PokerGFX JSON data
            nas_path: NAS file path (optional)

        Returns:
            Saved session record or None if duplicate
        """
        # Check for duplicate by file_hash
        existing = await self.get_by_file_hash(file_hash)
        if existing:
            logger.debug(f"Session already exists (hash: {file_hash[:16]}...)")
            return None

        # Extract queryable fields from JSON
        table_type = raw_json.get("Type", "UNKNOWN")
        event_title = raw_json.get("EventTitle", "")
        software_version = raw_json.get("SoftwareVersion", "")
        hand_count = len(raw_json.get("Hands", []))
        session_created_at = raw_json.get("CreatedDateTimeUTC")

        data = {
            "session_id": session_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "raw_json": raw_json,
            "table_type": table_type,
            "event_title": event_title,
            "software_version": software_version,
            "hand_count": hand_count,
            "session_created_at": session_created_at,
            "nas_path": nas_path,
            "sync_status": "synced",
        }

        try:
            result = await self.supabase.execute_with_retry(
                lambda: self.supabase.client.table("gfx_sessions")
                .insert(data)
                .execute()
            )
            logger.info(
                f"Saved session {session_id} ({hand_count} hands) - "
                f"type: {table_type}"
            )
            data_list = cast(list[dict[str, Any]], result.data)
            return data_list[0] if data_list else None

        except DuplicateSessionError:
            logger.debug(f"Duplicate session detected: {session_id}")
            return None

    async def get_by_file_hash(self, file_hash: str) -> dict[str, Any] | None:
        """Get session by file hash.

        Args:
            file_hash: SHA256 hash of file content

        Returns:
            Session record or None if not found
        """
        result = (
            self.supabase.client.table("gfx_sessions")
            .select("*")
            .eq("file_hash", file_hash)
            .limit(1)
            .execute()
        )
        data_list = cast(list[dict[str, Any]], result.data)
        return data_list[0] if data_list else None

    async def get_by_session_id(self, session_id: int) -> dict[str, Any] | None:
        """Get session by PokerGFX session ID.

        Args:
            session_id: PokerGFX session ID

        Returns:
            Session record or None if not found
        """
        result = (
            self.supabase.client.table("gfx_sessions")
            .select("*")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        data_list = cast(list[dict[str, Any]], result.data)
        return data_list[0] if data_list else None

    async def list_recent_sessions(
        self,
        limit: int = 50,
        table_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent sessions with optional filtering.

        Args:
            limit: Maximum number of sessions to return
            table_type: Filter by table type (e.g., "FEATURE_TABLE")

        Returns:
            List of session records
        """
        query = (
            self.supabase.client.table("gfx_sessions")
            .select("*")
            .order("processed_at", desc=True)
            .limit(limit)
        )

        if table_type:
            query = query.eq("table_type", table_type)

        result = query.execute()
        return cast(list[dict[str, Any]], result.data)

    async def get_session_hands(self, session_id: str) -> list[dict[str, Any]]:
        """Get hands from a session's raw JSON.

        Args:
            session_id: UUID of the session

        Returns:
            List of hand objects from the raw JSON
        """
        result = (
            self.supabase.client.table("gfx_sessions")
            .select("raw_json")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )

        data_list = cast(list[dict[str, Any]], result.data)
        if data_list:
            raw_json = data_list[0].get("raw_json", {})
            if isinstance(raw_json, dict):
                hands = raw_json.get("Hands", [])
                return cast(list[dict[str, Any]], hands)
        return []

    async def update_session(
        self,
        session_id: int,
        raw_json: dict[str, Any],
        file_hash: str,
    ) -> dict[str, Any] | None:
        """Update existing session with new data (for file modifications).

        Args:
            session_id: PokerGFX session ID
            raw_json: Updated complete JSON data
            file_hash: New file hash

        Returns:
            Updated session record or None if not found
        """
        hand_count = len(raw_json.get("Hands", []))

        data: dict[str, Any] = {
            "raw_json": raw_json,
            "file_hash": file_hash,
            "hand_count": hand_count,
            "sync_status": "updated",
        }

        try:
            result = await self.supabase.execute_with_retry(
                lambda: self.supabase.client.table("gfx_sessions")
                .update(data)
                .eq("session_id", session_id)
                .execute()
            )
            data_list = cast(list[dict[str, Any]], result.data)
            if data_list:
                logger.info(
                    f"Updated session {session_id} (now {hand_count} hands)"
                )
                return data_list[0]
            return None
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return None


class GFXHandsRepository:
    """Repository for individual hand operations.

    Stores hands separately from sessions for incremental sync support.
    When a file is modified, only new hands are added.
    """

    def __init__(self, supabase: SupabaseManager) -> None:
        """Initialize repository.

        Args:
            supabase: Supabase manager instance
        """
        self.supabase = supabase

    async def save_hands(
        self,
        session_id: int,
        hands: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Save multiple hands to Supabase.

        Uses upsert with hand_id as unique key to handle duplicates gracefully.

        Args:
            session_id: PokerGFX session ID
            hands: List of hand data dictionaries

        Returns:
            List of saved hand records
        """
        if not hands:
            return []

        records = []
        for hand in hands:
            hand_id = hand.get("ID")
            if hand_id is None:
                logger.warning(f"Hand missing ID, skipping: {hand}")
                continue

            # Extract board cards if available
            board_cards = None
            if "CommunityCards" in hand:
                board_cards = [
                    card.get("DisplayValue", "")
                    for card in hand.get("CommunityCards", [])
                ]

            # Count players
            player_count = len(hand.get("Players", []))

            records.append({
                "session_id": session_id,
                "hand_id": hand_id,
                "hand_number": hand.get("HandNumber"),
                "hand_data": hand,
                "board_cards": board_cards,
                "player_count": player_count,
            })

        if not records:
            return []

        try:
            # Use upsert to handle duplicates (hand_id is UNIQUE)
            result = await self.supabase.execute_with_retry(
                lambda: self.supabase.client.table("gfx_hands")
                .upsert(records, on_conflict="hand_id")
                .execute()
            )
            saved_count = len(result.data) if result.data else 0
            logger.info(f"Saved {saved_count} hands for session {session_id}")
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.error(f"Failed to save hands for session {session_id}: {e}")
            return []

    async def get_existing_hand_ids(self, session_id: int) -> set[int]:
        """Get set of existing hand IDs for a session.

        Args:
            session_id: PokerGFX session ID

        Returns:
            Set of hand IDs already stored
        """
        result = (
            self.supabase.client.table("gfx_hands")
            .select("hand_id")
            .eq("session_id", session_id)
            .execute()
        )
        data_list = cast(list[dict[str, Any]], result.data)
        return {int(row["hand_id"]) for row in data_list}

    async def get_new_hands(
        self,
        session_id: int,
        all_hands: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filter out already-stored hands, return only new ones.

        Args:
            session_id: PokerGFX session ID
            all_hands: Complete list of hands from file

        Returns:
            List of hands not yet in database
        """
        existing_ids = await self.get_existing_hand_ids(session_id)
        new_hands = [
            hand for hand in all_hands
            if hand.get("ID") is not None and hand["ID"] not in existing_ids
        ]
        logger.debug(
            f"Session {session_id}: {len(all_hands)} total, "
            f"{len(existing_ids)} existing, {len(new_hands)} new"
        )
        return new_hands

    async def get_hands_by_session(
        self,
        session_id: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get all hands for a session.

        Args:
            session_id: PokerGFX session ID
            limit: Maximum number of hands to return

        Returns:
            List of hand records
        """
        result = (
            self.supabase.client.table("gfx_hands")
            .select("*")
            .eq("session_id", session_id)
            .order("hand_number", desc=False)
            .limit(limit)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data)

    async def get_recent_hands(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get most recent hands across all sessions.

        Args:
            limit: Maximum number of hands to return

        Returns:
            List of hand records
        """
        result = (
            self.supabase.client.table("gfx_hands")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data)

    async def count_hands_by_session(self, session_id: int) -> int:
        """Count total hands for a session.

        Args:
            session_id: PokerGFX session ID

        Returns:
            Number of hands stored
        """
        result = (
            self.supabase.client.table("gfx_hands")
            .select("id", count="exact")  # type: ignore[arg-type]
            .eq("session_id", session_id)
            .execute()
        )
        return result.count or 0


class SyncLogRepository:
    """Repository for sync log operations.

    Tracks NAS file synchronization for auditing and duplicate detection.
    """

    def __init__(self, supabase: SupabaseManager) -> None:
        """Initialize repository.

        Args:
            supabase: Supabase manager instance
        """
        self.supabase = supabase

    async def log_sync_start(
        self,
        file_name: str,
        file_path: str,
        file_hash: str,
        file_size_bytes: int | None = None,
        operation: str = "created",
    ) -> dict[str, Any]:
        """Log start of sync operation.

        Args:
            file_name: Name of the file
            file_path: Full path to the file
            file_hash: SHA256 hash of file content
            file_size_bytes: Size of the file in bytes
            operation: Type of operation (created, modified, etc.)

        Returns:
            Created log record
        """
        data = {
            "file_name": file_name,
            "file_path": file_path,
            "file_hash": file_hash,
            "file_size_bytes": file_size_bytes,
            "operation": operation,
            "status": "processing",
        }

        result = (
            self.supabase.client.table("sync_log").insert(data).execute()
        )
        data_list = cast(list[dict[str, Any]], result.data)
        return data_list[0]

    async def log_sync_complete(
        self,
        log_id: str,
        session_id: str | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Log completion of sync operation.

        Args:
            log_id: UUID of the sync log entry
            session_id: UUID of the created session (if successful)
            status: Final status (success, failed, skipped)
            error_message: Error message (if failed)
        """
        data: dict[str, Any] = {
            "status": status,
            "completed_at": datetime.now(UTC).isoformat(),
        }

        if session_id:
            data["session_id"] = session_id
        if error_message:
            data["error_message"] = error_message

        self.supabase.client.table("sync_log").update(data).eq(
            "id", log_id
        ).execute()

    async def is_file_processed(self, file_hash: str) -> bool:
        """Check if file has been successfully processed.

        Args:
            file_hash: SHA256 hash of file content

        Returns:
            True if file was successfully synced
        """
        result = (
            self.supabase.client.table("sync_log")
            .select("id")
            .eq("file_hash", file_hash)
            .eq("status", "success")
            .limit(1)
            .execute()
        )
        data_list = cast(list[dict[str, Any]], result.data)
        return len(data_list) > 0

    async def get_recent_logs(
        self,
        limit: int = 100,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent sync logs.

        Args:
            limit: Maximum number of logs to return
            status: Filter by status (optional)

        Returns:
            List of sync log records
        """
        query = (
            self.supabase.client.table("sync_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )

        if status:
            query = query.eq("status", status)

        result = query.execute()
        return cast(list[dict[str, Any]], result.data)

    async def get_failed_syncs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get failed sync operations for retry.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of failed sync log records
        """
        result = (
            self.supabase.client.table("sync_log")
            .select("*")
            .eq("status", "failed")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data)

    async def increment_retry_count(self, log_id: str) -> None:
        """Increment retry count for a sync log entry.

        Args:
            log_id: UUID of the sync log entry
        """
        # Get current retry count
        result = (
            self.supabase.client.table("sync_log")
            .select("retry_count")
            .eq("id", log_id)
            .limit(1)
            .execute()
        )

        data_list = cast(list[dict[str, Any]], result.data)
        if data_list:
            current_count = data_list[0].get("retry_count", 0) or 0
            self.supabase.client.table("sync_log").update(
                {"retry_count": int(current_count) + 1, "status": "processing"}
            ).eq("id", log_id).execute()
