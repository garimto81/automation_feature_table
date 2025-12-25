"""WebSocket overlay server for real-time broadcast graphics."""

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from src.config.settings import OutputSettings
from src.models.hand import FusedHandResult

logger = logging.getLogger(__name__)


class OverlayServer:
    """WebSocket server for broadcast overlay."""

    def __init__(self, settings: OutputSettings):
        self.settings = settings
        self._clients: set[WebSocketServerProtocol] = set()
        self._server: Optional[websockets.WebSocketServer] = None
        self._running = False

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self._handle_client,
            "0.0.0.0",
            self.settings.overlay_ws_port,
        )
        self._running = True
        logger.info(f"Overlay server started on port {self.settings.overlay_ws_port}")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        self._running = False

        # Close all client connections
        for client in self._clients.copy():
            await client.close()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("Overlay server stopped")

    async def _handle_client(
        self,
        websocket: WebSocketServerProtocol,
        path: str,
    ) -> None:
        """Handle incoming WebSocket connections."""
        self._clients.add(websocket)
        client_info = f"{websocket.remote_address}"
        logger.info(f"Overlay client connected: {client_info}")

        try:
            # Send welcome message
            await websocket.send(
                json.dumps(
                    {
                        "type": "connected",
                        "message": "Poker Hand Overlay Server",
                    }
                )
            )

            # Keep connection alive
            async for message in websocket:
                try:
                    data = json.loads(message)

                    # Handle client requests
                    if data.get("type") == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                    elif data.get("type") == "subscribe":
                        table_id = data.get("table_id")
                        logger.info(f"Client {client_info} subscribed to {table_id}")

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {message}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(f"Overlay client disconnected: {client_info}")

    async def broadcast_hand_result(self, result: FusedHandResult) -> None:
        """Broadcast hand result to all connected clients."""
        if not self._clients:
            return

        message = json.dumps(
            {
                "type": "hand_result",
                "table_id": result.table_id,
                "hand_number": result.hand_number,
                "hand_rank": result.rank_name,
                "is_premium": result.is_premium,
                "confidence": result.confidence,
                "source": result.source.value,
                "cross_validated": result.cross_validated,
                "timestamp": result.timestamp.isoformat(),
            }
        )

        # Broadcast to all clients
        disconnected = set()
        for client in self._clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)

        # Remove disconnected clients
        self._clients -= disconnected

        logger.debug(f"Broadcast to {len(self._clients)} clients: {result.rank_name}")

    async def send_table_update(
        self,
        table_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """Send table-specific update."""
        message = json.dumps(
            {
                "type": "table_update",
                "table_id": table_id,
                "event": event_type,
                "data": data,
            }
        )

        for client in self._clients.copy():
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                self._clients.discard(client)

    def get_client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)


# HTML template for overlay (can be served separately)
OVERLAY_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Poker Hand Overlay</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: 'Segoe UI', Arial, sans-serif;
            background: transparent;
        }
        .hand-display {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 10px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            font-size: 24px;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        .hand-display.visible {
            opacity: 1;
        }
        .hand-display.premium {
            background: linear-gradient(135deg, #FFD700, #FFA500);
            color: black;
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        .table-id {
            font-size: 14px;
            opacity: 0.7;
            margin-bottom: 5px;
        }
        .rank {
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div id="overlay" class="hand-display">
        <div class="table-id">Table 1</div>
        <div class="rank">Royal Flush</div>
    </div>

    <script>
        const overlay = document.getElementById('overlay');
        const ws = new WebSocket(`ws://${location.hostname}:8081`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'hand_result') {
                showHand(data);
            }
        };

        function showHand(data) {
            overlay.querySelector('.table-id').textContent = data.table_id;
            overlay.querySelector('.rank').textContent = data.hand_rank;

            overlay.classList.remove('premium');
            if (data.is_premium) {
                overlay.classList.add('premium');
            }

            overlay.classList.add('visible');

            // Hide after 5 seconds
            setTimeout(() => {
                overlay.classList.remove('visible');
            }, 5000);
        }
    </script>
</body>
</html>
"""
