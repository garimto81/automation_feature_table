"""PokerGFX WebSocket client for receiving hand events."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed

from src.config.settings import PokerGFXSettings
from src.models.hand import Card, HandResult, PlayerInfo
from src.primary.hand_classifier import HandClassifier

logger = logging.getLogger(__name__)


@dataclass
class HandSession:
    """Track hand session state for a table."""

    table_id: str
    hand_number: int
    start_time: datetime
    dealer_seat: int | None = None
    small_blind: int | None = None
    big_blind: int | None = None
    end_time: datetime | None = None
    completed: bool = False


class PokerGFXClient:
    """WebSocket client for PokerGFX JSON API."""

    def __init__(
        self,
        settings: PokerGFXSettings,
        classifier: HandClassifier | None = None,
    ):
        self.settings = settings
        self.classifier = classifier or HandClassifier()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._handlers: list[Callable[[HandResult], None]] = []
        self._active_sessions: dict[str, HandSession] = {}  # table_id -> session

    async def connect(self) -> None:
        """Establish WebSocket connection to PokerGFX."""
        url = f"{self.settings.api_url}?api_key={self.settings.api_key}"
        logger.info(f"Connecting to PokerGFX at {self.settings.api_url}")

        try:
            self._ws = await websockets.connect(url)
            logger.info("Connected to PokerGFX")
        except Exception as e:
            logger.error(f"Failed to connect to PokerGFX: {e}")
            raise

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("Disconnected from PokerGFX")

    def add_handler(self, handler: Callable[[HandResult], None]) -> None:
        """Add a handler for processed hand results."""
        self._handlers.append(handler)

    async def _reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff."""
        for attempt in range(self.settings.max_retries):
            wait_time = self.settings.reconnect_interval * (2**attempt)
            logger.info(f"Reconnecting in {wait_time}s (attempt {attempt + 1})")
            await asyncio.sleep(wait_time)

            try:
                await self.connect()
                return True
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed: {e}")

        return False

    def _validate_cards(self, players: list[dict], community_cards: list[Card]) -> bool:
        """Validate that all cards are unique (no duplicates in 52-card deck)."""
        seen_cards = set()

        # Check community cards
        for card in community_cards:
            card_str = str(card)
            if card_str in seen_cards:
                logger.error(f"Duplicate card detected in community: {card_str}")
                return False
            seen_cards.add(card_str)

        # Check player hole cards
        for player in players:
            hole_cards = player.get("hole_cards", [])
            for card in hole_cards:
                card_str = str(card)
                if card_str in seen_cards:
                    logger.error(
                        f"Duplicate card detected for {player.get('name')}: {card_str}"
                    )
                    return False
                seen_cards.add(card_str)

        return True

    def _handle_hand_start(self, data: dict) -> None:
        """Handle hand_start event - track session."""
        table_id = data.get("table_id", "unknown")
        hand_number = data.get("hand_number", 0)
        timestamp = datetime.fromisoformat(
            data.get("timestamp", datetime.now().isoformat())
        )

        session = HandSession(
            table_id=table_id,
            hand_number=hand_number,
            start_time=timestamp,
            dealer_seat=data.get("dealer_seat"),
            small_blind=data.get("small_blind"),
            big_blind=data.get("big_blind"),
        )

        self._active_sessions[table_id] = session
        logger.info(
            f"Hand #{hand_number} started on {table_id} "
            f"(BB: {session.big_blind})"
        )

    def _handle_hand_end(self, data: dict) -> None:
        """Handle hand_end event - mark session complete."""
        table_id = data.get("table_id", "unknown")
        hand_number = data.get("hand_number", 0)
        timestamp = datetime.fromisoformat(
            data.get("timestamp", datetime.now().isoformat())
        )

        session = self._active_sessions.get(table_id)
        if session and session.hand_number == hand_number:
            session.end_time = timestamp
            session.completed = True
            duration = (timestamp - session.start_time).total_seconds()
            logger.info(
                f"Hand #{hand_number} ended on {table_id} "
                f"(duration: {duration:.1f}s, winner: {data.get('winner')})"
            )

    def _parse_hand_event(self, data: dict) -> HandResult | None:
        """Parse PokerGFX JSON event into HandResult."""
        try:
            event_type = data.get("event")

            # Handle hand_start event
            if event_type == "hand_start":
                self._handle_hand_start(data)
                return None

            # Handle hand_end event
            if event_type == "hand_end":
                self._handle_hand_end(data)
                return None

            # Only process completed hands
            if event_type != "hand_complete":
                return None

            # Parse players
            players = []
            for p in data.get("players", []):
                player = PlayerInfo.from_dict(p)
                players.append({
                    "name": player.name,
                    "seat": player.seat,
                    "hole_cards": player.hole_cards,
                    "stack": player.stack,
                })

            # Parse community cards
            community_cards = [
                Card.from_string(c) for c in data.get("community_cards", [])
            ]

            # Validate no duplicate cards
            if not self._validate_cards(players, community_cards):
                logger.error(f"Invalid hand #{data.get('hand_number')}: duplicate cards")
                return None

            # Find best hand and classify
            best = self.classifier.find_best_hand(players, community_cards)

            if not best:
                logger.warning(f"No valid hands in event: {data.get('hand_number')}")
                return None

            # Build players showdown info
            players_showdown = []
            for p in players:
                if p.get("hole_cards"):
                    result = self.classifier.classify(p["hole_cards"], community_cards)
                    players_showdown.append({
                        "player": p["name"],
                        "rank_value": result["rank_value"],
                        "rank_name": result["rank_name"],
                    })

            return HandResult(
                table_id=data.get("table_id", "unknown"),
                hand_number=data.get("hand_number", 0),
                hand_rank=best["hand_rank"],
                rank_value=best["rank_value"],
                is_premium=best["hand_rank"].is_premium,
                confidence=1.0,  # RFID data is 100% accurate
                players_showdown=players_showdown,
                pot_size=data.get("pot", 0),
                timestamp=datetime.fromisoformat(
                    data.get("timestamp", datetime.now().isoformat())
                ),
                community_cards=community_cards,
                winner=data.get("winner"),
            )

        except Exception as e:
            logger.error(f"Failed to parse hand event: {e}")
            return None

    async def listen(self) -> AsyncIterator[HandResult]:
        """Listen for hand events and yield processed results."""
        self._running = True

        while self._running:
            try:
                if not self._ws:
                    await self.connect()

                async for message in self._ws:
                    if not self._running:
                        break

                    try:
                        data = json.loads(message)
                        result = self._parse_hand_event(data)

                        if result:
                            logger.info(
                                f"Hand #{result.hand_number} on {result.table_id}: "
                                f"{result.rank_name} (pot: {result.pot_size})"
                            )

                            # Call registered handlers
                            for handler in self._handlers:
                                try:
                                    handler(result)
                                except Exception as e:
                                    logger.error(f"Handler error: {e}")

                            yield result

                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON received: {e}")

            except ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
                if self._running:
                    if not await self._reconnect():
                        logger.error("Max reconnection attempts reached")
                        break

            except Exception as e:
                logger.error(f"Error in listen loop: {e}")
                if self._running:
                    await asyncio.sleep(self.settings.reconnect_interval)

    async def get_hand_history(
        self,
        table_id: str,
        limit: int = 100,
    ) -> list[HandResult]:
        """
        Request hand history for a table.

        Note: This is a placeholder - actual implementation depends on
        PokerGFX API specification.
        """
        if not self._ws:
            await self.connect()

        request = {
            "action": "get_history",
            "table_id": table_id,
            "limit": limit,
        }

        await self._ws.send(json.dumps(request))
        response = await self._ws.recv()
        data = json.loads(response)

        results = []
        for hand_data in data.get("hands", []):
            result = self._parse_hand_event(hand_data)
            if result:
                results.append(result)

        return results
