"""Recording manager for coordinating hand recordings."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.recording.session import RecordingSession, RecordingStatus
from src.recording.storage import StorageManager
from src.vmix.replay_controller import HandRecordingResult, ReplayController

if TYPE_CHECKING:
    from src.config.settings import RecordingSettings
    from src.vmix.client import VMixClient

logger = logging.getLogger(__name__)


class RecordingManager:
    """Manages recording sessions across multiple tables.

    Coordinates vMix replay controller with storage management
    to provide a unified recording interface.
    """

    def __init__(
        self,
        settings: "RecordingSettings",
        vmix_client: "VMixClient",
        on_recording_complete: Callable[[RecordingSession], None] | None = None,
    ):
        self.settings = settings
        self.vmix_client = vmix_client
        self._on_recording_complete = on_recording_complete

        # Initialize components
        self.storage = StorageManager(settings)
        self.storage.ensure_directories()

        # Per-table replay controllers
        self._controllers: dict[str, ReplayController] = {}

        # Active sessions
        self._active_sessions: dict[str, RecordingSession] = {}

        # Session history
        self._completed_sessions: list[RecordingSession] = []
        self._max_history: int = 100

    def _get_controller(self, table_id: str) -> ReplayController:
        """Get or create replay controller for a table."""
        if table_id not in self._controllers:
            self._controllers[table_id] = ReplayController(
                client=self.vmix_client,
                on_recording_complete=self._handle_vmix_complete,
            )
        return self._controllers[table_id]

    async def start_recording(
        self,
        table_id: str,
        hand_number: int,
        vmix_input_number: int | None = None,
    ) -> RecordingSession | None:
        """Start recording for a hand.

        Args:
            table_id: Table identifier
            hand_number: Hand number to record
            vmix_input_number: Optional vMix input number

        Returns:
            RecordingSession if started successfully, None otherwise
        """
        # Check if already recording for this table
        if table_id in self._active_sessions:
            existing = self._active_sessions[table_id]
            logger.warning(
                f"Already recording {table_id} #{existing.hand_number}. "
                f"Stopping before starting #{hand_number}"
            )
            await self.stop_recording(table_id)

        # Create session
        session = RecordingSession(
            table_id=table_id,
            hand_number=hand_number,
            vmix_input_number=vmix_input_number,
        )

        # Start vMix recording
        controller = self._get_controller(table_id)
        success = await controller.start_hand_recording(
            table_id=table_id,
            hand_number=hand_number,
            start_main_recording=True,
        )

        if success:
            session.start()
            self._active_sessions[table_id] = session
            logger.info(f"Recording started: {table_id} #{hand_number}")
            return session
        else:
            session.fail("Failed to start vMix recording")
            return None

    async def stop_recording(
        self,
        table_id: str,
        export_event: bool = True,
    ) -> RecordingSession | None:
        """Stop recording for a table.

        Args:
            table_id: Table identifier
            export_event: Whether to export the replay event

        Returns:
            Completed RecordingSession, or None if no active recording
        """
        if table_id not in self._active_sessions:
            logger.warning(f"No active recording for {table_id}")
            return None

        session = self._active_sessions.pop(table_id)
        controller = self._get_controller(table_id)

        # Stop vMix recording
        result = await controller.end_hand_recording(export_event=export_event)

        if result and result.success:
            # Generate file path
            file_path = self.storage.get_full_path(
                table_id=table_id,
                hand_number=session.hand_number,
                timestamp=session.started_at,
            )

            session.complete(
                file_path=str(file_path),
                file_name=file_path.name,
            )

            # Add to history
            self._add_to_history(session)

            # Call callback
            if self._on_recording_complete:
                self._on_recording_complete(session)

            logger.info(
                f"Recording stopped: {table_id} #{session.hand_number} "
                f"({session.duration_seconds}s)"
            )
        else:
            error_msg = result.error_message if result else "Unknown error"
            session.fail(error_msg or "Unknown error")
            self._add_to_history(session)

        return session

    async def cancel_recording(self, table_id: str) -> RecordingSession | None:
        """Cancel recording for a table without saving.

        Args:
            table_id: Table identifier

        Returns:
            Cancelled RecordingSession, or None if no active recording
        """
        if table_id not in self._active_sessions:
            logger.warning(f"No active recording to cancel for {table_id}")
            return None

        session = self._active_sessions.pop(table_id)
        controller = self._get_controller(table_id)

        await controller.cancel_hand_recording()
        session.cancel()
        self._add_to_history(session)

        logger.info(f"Recording cancelled: {table_id} #{session.hand_number}")
        return session

    def _handle_vmix_complete(self, result: HandRecordingResult) -> None:
        """Handle vMix recording completion callback."""
        logger.debug(
            f"vMix recording complete: {result.table_id} #{result.hand_number} "
            f"({result.duration_seconds}s)"
        )

    def _add_to_history(self, session: RecordingSession) -> None:
        """Add session to history, maintaining max size."""
        self._completed_sessions.append(session)
        if len(self._completed_sessions) > self._max_history:
            self._completed_sessions = self._completed_sessions[-self._max_history:]

    def get_active_session(self, table_id: str) -> RecordingSession | None:
        """Get active recording session for a table."""
        return self._active_sessions.get(table_id)

    def get_all_active_sessions(self) -> dict[str, RecordingSession]:
        """Get all active recording sessions."""
        return self._active_sessions.copy()

    def get_session_history(
        self,
        table_id: str | None = None,
        limit: int = 50,
    ) -> list[RecordingSession]:
        """Get completed session history.

        Args:
            table_id: Optional filter by table
            limit: Maximum number of sessions to return

        Returns:
            List of sessions (newest first)
        """
        sessions = self._completed_sessions.copy()
        sessions.reverse()

        if table_id:
            sessions = [s for s in sessions if s.table_id == table_id]

        return sessions[:limit]

    def get_stats(self) -> dict[str, object]:
        """Get recording statistics."""
        total_completed = len([s for s in self._completed_sessions if s.is_completed])
        total_failed = len(
            [s for s in self._completed_sessions if s.status == RecordingStatus.FAILED]
        )
        total_cancelled = len(
            [
                s
                for s in self._completed_sessions
                if s.status == RecordingStatus.CANCELLED
            ]
        )

        total_duration = sum(
            s.duration_seconds or 0
            for s in self._completed_sessions
            if s.is_completed
        )

        return {
            "active_recordings": len(self._active_sessions),
            "active_tables": list(self._active_sessions.keys()),
            "total_completed": total_completed,
            "total_failed": total_failed,
            "total_cancelled": total_cancelled,
            "total_duration_seconds": total_duration,
            "storage": self.storage.get_storage_stats(),
        }

    async def stop_all(self) -> list[RecordingSession]:
        """Stop all active recordings.

        Returns:
            List of stopped sessions
        """
        stopped = []
        for table_id in list(self._active_sessions.keys()):
            session = await self.stop_recording(table_id)
            if session:
                stopped.append(session)

        logger.info(f"Stopped {len(stopped)} active recordings")
        return stopped
