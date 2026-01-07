"""WebSocket server for real-time dashboard updates (PRD-0008).

Provides 1-second interval broadcasting of:
- Table status (Primary/Secondary connection, current hand)
- Grade distribution (A/B/C counts)
- Recording sessions (active, completed)
- System health (service status, latency)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from src.database.monitoring_repository import MonitoringRepository

logger = logging.getLogger(__name__)


@dataclass
class DashboardState:
    """Current dashboard state for broadcasting."""

    table_statuses: list[dict[str, Any]] = field(default_factory=list)
    grade_distribution: dict[str, int] = field(default_factory=dict)
    recording_sessions: list[dict[str, Any]] = field(default_factory=list)
    system_health: dict[str, dict[str, Any]] = field(default_factory=dict)
    today_stats: dict[str, Any] = field(default_factory=dict)
    last_updated: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "table_statuses": self.table_statuses,
            "grade_distribution": self.grade_distribution,
            "recording_sessions": self.recording_sessions,
            "system_health": self.system_health,
            "today_stats": self.today_stats,
            "last_updated": self.last_updated,
        }


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Dashboard client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"Dashboard client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            return

        message_json = json.dumps(message)
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


class DashboardWebSocket:
    """WebSocket server for dashboard real-time updates."""

    def __init__(
        self,
        monitoring_repo: "MonitoringRepository | None" = None,
        broadcast_interval: float = 1.0,
    ):
        self.monitoring_repo = monitoring_repo
        self.broadcast_interval = broadcast_interval
        self.manager = ConnectionManager()
        self._broadcast_task: asyncio.Task[None] | None = None
        self._running = False
        self._state = DashboardState()

    async def start_broadcasting(self) -> None:
        """Start the background broadcast loop."""
        if self._running:
            logger.warning("Broadcast loop already running")
            return

        self._running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info(f"Dashboard broadcast started (interval: {self.broadcast_interval}s)")

    async def stop_broadcasting(self) -> None:
        """Stop the background broadcast loop."""
        self._running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None
        logger.info("Dashboard broadcast stopped")

    async def _broadcast_loop(self) -> None:
        """Background loop that fetches data and broadcasts to clients."""
        while self._running:
            try:
                # Only fetch and broadcast if there are connections
                if self.manager.connection_count > 0:
                    await self._update_state()
                    await self.manager.broadcast(self._state.to_dict())

                await asyncio.sleep(self.broadcast_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast loop error: {e}")
                await asyncio.sleep(self.broadcast_interval)

    async def _update_state(self) -> None:
        """Update dashboard state from database."""
        if not self.monitoring_repo:
            # Use mock data if no repository
            self._state = self._get_mock_state()
            return

        try:
            # Fetch all data concurrently
            table_statuses, health_logs, active_sessions, today_stats = await asyncio.gather(
                self.monitoring_repo.get_all_table_statuses(),
                self.monitoring_repo.get_all_latest_health(),
                self.monitoring_repo.get_active_recording_sessions(),
                self.monitoring_repo.get_today_stats(),
            )

            self._state = DashboardState(
                table_statuses=[
                    {
                        "table_id": s.table_id,
                        "primary_connected": s.primary_connected,
                        "secondary_connected": s.secondary_connected,
                        "current_hand_number": s.current_hand_number,
                        "hand_start_time": (
                            s.hand_start_time.isoformat() if s.hand_start_time else None
                        ),
                        "last_fusion_result": s.last_fusion_result,
                    }
                    for s in table_statuses
                ],
                grade_distribution=(
                    today_stats.get("grade_distribution")  # type: ignore[arg-type]
                    if isinstance(today_stats.get("grade_distribution"), dict)
                    else {}
                ),
                recording_sessions=[
                    {
                        "session_id": rs.session_id,
                        "table_id": rs.table_id,
                        "status": rs.status,
                        "start_time": rs.start_time.isoformat(),
                        "file_size_mb": rs.file_size_mb,
                    }
                    for rs in active_sessions
                ],
                system_health={
                    name: {
                        "status": log.status,
                        "latency_ms": log.latency_ms,
                        "message": log.message,
                        "last_check": log.created_at.isoformat(),
                    }
                    for name, log in health_logs.items()
                },
                today_stats=today_stats,
                last_updated=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error(f"Failed to update dashboard state: {e}")

    def _get_mock_state(self) -> DashboardState:
        """Get mock state for testing without database."""
        return DashboardState(
            table_statuses=[
                {
                    "table_id": "table_a",
                    "primary_connected": True,
                    "secondary_connected": True,
                    "current_hand_number": 142,
                    "hand_start_time": datetime.now(UTC).isoformat(),
                    "last_fusion_result": "validated",
                },
                {
                    "table_id": "table_b",
                    "primary_connected": True,
                    "secondary_connected": False,
                    "current_hand_number": 98,
                    "hand_start_time": datetime.now(UTC).isoformat(),
                    "last_fusion_result": "review",
                },
            ],
            grade_distribution={"A": 5, "B": 12, "C": 28},
            recording_sessions=[
                {
                    "session_id": "session_001",
                    "table_id": "table_a",
                    "status": "recording",
                    "start_time": datetime.now(UTC).isoformat(),
                    "file_size_mb": 256.5,
                },
            ],
            system_health={
                "PostgreSQL": {"status": "connected", "latency_ms": 12, "message": None},
                "PokerGFX": {"status": "connected", "latency_ms": 45, "message": None},
                "Gemini API": {"status": "connected", "latency_ms": 120, "message": "Quota: 85%"},
                "vMix": {"status": "connected", "latency_ms": 8, "message": "Recording"},
            },
            today_stats={
                "total_hands": 45,
                "broadcast_eligible": 17,
                "broadcast_ratio": 37.8,
                "completed_sessions": 3,
                "total_storage_gb": 4.2,
            },
            last_updated=datetime.now(UTC).isoformat(),
        )

    async def handle_connection(self, websocket: WebSocket) -> None:
        """Handle a WebSocket connection lifecycle."""
        await self.manager.connect(websocket)

        # Send initial state immediately
        await websocket.send_text(json.dumps(self._state.to_dict()))

        try:
            while True:
                # Keep connection alive, handle any client messages
                data = await websocket.receive_text()
                # Currently just echo or ignore client messages
                logger.debug(f"Received from client: {data}")

        except WebSocketDisconnect:
            self.manager.disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            self.manager.disconnect(websocket)

    @property
    def state(self) -> DashboardState:
        """Get current dashboard state."""
        return self._state


def create_dashboard_routes(dashboard: DashboardWebSocket) -> None:
    """Create FastAPI routes for the dashboard WebSocket.

    Usage:
        from fastapi import FastAPI
        from src.dashboard import DashboardWebSocket

        app = FastAPI()
        dashboard = DashboardWebSocket(monitoring_repo)

        @app.on_event("startup")
        async def startup():
            await dashboard.start_broadcasting()

        @app.websocket("/ws/dashboard")
        async def websocket_endpoint(websocket: WebSocket):
            await dashboard.handle_connection(websocket)
    """
    pass  # Routes are created by the caller using handle_connection
