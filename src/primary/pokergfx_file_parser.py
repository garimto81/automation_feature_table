"""PokerGFX JSON file parser based on PRD-0002 schema."""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from phevaluator import evaluate_cards

from src.models.hand import Card, HandRank, HandResult, PlayerInfo

logger = logging.getLogger(__name__)


@dataclass
class ParsedSession:
    """Parsed PokerGFX session data."""

    session_id: int
    created_at: datetime
    software_version: str
    table_type: str
    event_title: str
    hands: list["ParsedHand"]


@dataclass
class ParsedHand:
    """Parsed hand data from PokerGFX JSON."""

    hand_num: int
    game_variant: str
    duration_seconds: int
    start_time: datetime
    players: list[PlayerInfo]
    community_cards: list[Card]
    events: list[dict[str, Any]]
    pot_size: int
    winner: str | None


class PokerGFXFileParser:
    """Parser for PokerGFX JSON session files (PRD-0002 schema).

    PokerGFX exports session files containing multiple hands with the structure:
    {
        "CreatedDateTimeUTC": "2025-10-16T08:25:17Z",
        "Hands": [...],
        "ID": 638961999170907267,
        "Type": "FEATURE_TABLE"
    }
    """

    # phevaluator rank thresholds for hand classification
    RANK_THRESHOLDS = [
        (1, 1, HandRank.ROYAL_FLUSH),
        (2, 10, HandRank.STRAIGHT_FLUSH),
        (11, 166, HandRank.FOUR_OF_A_KIND),
        (167, 322, HandRank.FULL_HOUSE),
        (323, 1599, HandRank.FLUSH),
        (1600, 1609, HandRank.STRAIGHT),
        (1610, 2467, HandRank.THREE_OF_A_KIND),
        (2468, 3325, HandRank.TWO_PAIR),
        (3326, 6185, HandRank.ONE_PAIR),
        (6186, 7462, HandRank.HIGH_CARD),
    ]

    def parse_file(self, filepath: Path) -> list[HandResult]:
        """Parse a PokerGFX JSON file and return HandResult list.

        Args:
            filepath: Path to the JSON file

        Returns:
            List of HandResult objects for each player's hand in the session
        """
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        return self.parse_session_data(data)

    def parse_session_data(self, data: dict[str, Any]) -> list[HandResult]:
        """Parse session JSON data and return HandResult list.

        Args:
            data: Parsed JSON data dictionary

        Returns:
            List of HandResult objects
        """
        results: list[HandResult] = []
        table_id = self._extract_table_id(data)

        for hand_data in data.get("Hands", []):
            hand_results = self._parse_hand(hand_data, table_id)
            results.extend(hand_results)

        logger.info(f"Parsed {len(results)} hand results from session")
        return results

    def _extract_table_id(self, data: dict[str, Any]) -> str:
        """Extract table ID from session data."""
        table_type = data.get("Type", "UNKNOWN")
        session_id = data.get("ID", 0)
        return f"{table_type}_{session_id}"

    def _parse_hand(
        self, hand_data: dict[str, Any], table_id: str
    ) -> list[HandResult]:
        """Parse a single hand and return HandResult for each showdown player.

        Args:
            hand_data: Hand JSON data
            table_id: Table identifier

        Returns:
            List of HandResult objects (one per player with hole cards)
        """
        results: list[HandResult] = []

        hand_num = hand_data.get("HandNum", 0)
        start_time = self._parse_datetime(hand_data.get("StartDateTimeUTC", ""))

        # Extract community cards from events
        community_cards = self._extract_community_cards(hand_data.get("Events", []))

        # Get pot size from last event
        pot_size = self._extract_final_pot(hand_data.get("Events", []))

        # Find winner from events
        winner = self._find_winner(hand_data)

        # Process each player with hole cards
        for player_data in hand_data.get("Players", []):
            hole_cards_raw = player_data.get("HoleCards", [])

            # Handle space-separated card string format: ['10d 9d'] -> ['10d', '9d']
            if hole_cards_raw and len(hole_cards_raw) == 1 and ' ' in hole_cards_raw[0]:
                hole_cards_raw = hole_cards_raw[0].split()

            # Skip players without hole cards (didn't show)
            if not hole_cards_raw or len(hole_cards_raw) < 2 or hole_cards_raw[0] == '':
                continue

            # Need at least 3 community cards for evaluation
            if len(community_cards) < 3:
                continue

            # Convert cards to phevaluator format
            hole_cards = [self._convert_card(c) for c in hole_cards_raw]
            board_cards = [str(c) for c in community_cards[:5]]

            # Evaluate hand using phevaluator
            all_cards = hole_cards + board_cards
            if len(all_cards) >= 5:
                try:
                    rank_value = evaluate_cards(*all_cards[:7])
                    hand_rank = self._get_hand_rank(rank_value)
                except Exception as e:
                    logger.warning(f"Hand evaluation failed: {e}")
                    rank_value = 7462  # Worst high card
                    hand_rank = HandRank.HIGH_CARD
            else:
                rank_value = 7462
                hand_rank = HandRank.HIGH_CARD

            # Create player info
            player_info = PlayerInfo(
                seat=player_data.get("PlayerNum", 0),
                name=player_data.get("Name", ""),
                hole_cards=[Card.from_string(c) for c in hole_cards],
                stack=player_data.get("EndStackAmt", 0),
            )

            # Create showdown dict for HandResult
            showdown_info = {
                "seat": player_info.seat,
                "name": player_info.name,
                "hole_cards": hole_cards_raw,
                "rank_name": hand_rank.display_name,
                "rank_value": rank_value,
            }

            result = HandResult(
                table_id=table_id,
                hand_number=hand_num,
                hand_rank=hand_rank,
                rank_value=rank_value,
                is_premium=hand_rank.is_premium,
                confidence=1.0,  # RFID data is always reliable
                players_showdown=[showdown_info],
                pot_size=pot_size,
                timestamp=start_time or datetime.now(),
                community_cards=[Card.from_string(c) for c in board_cards],
                winner=winner,
            )

            results.append(result)

        return results

    def _convert_card(self, pokergfx_card: str) -> str:
        """Convert PokerGFX card format to phevaluator format.

        PokerGFX uses: 7s, jd, as, 10h (lowercase, 10 for ten)
        phevaluator uses: 7s, Jd, As, Th (uppercase face cards, T for ten)

        Args:
            pokergfx_card: Card in PokerGFX format (e.g., "7s", "jd", "10h")

        Returns:
            Card in phevaluator format (e.g., "7s", "Jd", "Th")
        """
        if not pokergfx_card:
            raise ValueError("Empty card string")

        # Extract rank and suit
        suit = pokergfx_card[-1].lower()
        rank = pokergfx_card[:-1]

        # Convert rank
        if rank == "10":
            rank = "T"
        elif rank.lower() in ("j", "q", "k", "a"):
            rank = rank.upper()
        else:
            rank = rank  # Numbers stay as-is

        return f"{rank}{suit}"

    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration string to seconds.

        Args:
            duration_str: Duration like "PT2M56.2628165S"

        Returns:
            Duration in seconds (integer)
        """
        if not duration_str:
            return 0

        # Pattern for ISO 8601 duration: PT{hours}H{minutes}M{seconds}S
        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?"
        match = re.match(pattern, duration_str)

        if not match:
            logger.warning(f"Could not parse duration: {duration_str}")
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = float(match.group(3) or 0)

        return int(hours * 3600 + minutes * 60 + seconds)

    def _parse_datetime(self, dt_str: str) -> datetime | None:
        """Parse ISO 8601 datetime string.

        Args:
            dt_str: Datetime like "2025-10-16T08:25:17.0907267Z"

        Returns:
            datetime object or None
        """
        if not dt_str:
            return None

        try:
            # Remove microseconds beyond 6 digits if present
            # Python's fromisoformat doesn't handle 7+ digit microseconds
            if "." in dt_str:
                main_part, frac_part = dt_str.rsplit(".", 1)
                # Remove 'Z' and truncate to 6 digits
                frac_clean = frac_part.rstrip("Z")[:6]
                dt_str = f"{main_part}.{frac_clean}+00:00"
            else:
                dt_str = dt_str.replace("Z", "+00:00")

            return datetime.fromisoformat(dt_str)
        except ValueError as e:
            logger.warning(f"Could not parse datetime: {dt_str} - {e}")
            return None

    def _extract_community_cards(self, events: list[dict[str, Any]]) -> list[Card]:
        """Extract community cards from event list.

        Args:
            events: List of event dictionaries

        Returns:
            List of Card objects representing the board
        """
        cards: list[Card] = []

        for event in events:
            if event.get("EventType") == "BOARD CARD":
                board_cards = event.get("BoardCards")
                if not board_cards:
                    continue

                # Handle both string ("6d") and list (["6d", "7h"]) formats
                if isinstance(board_cards, str):
                    card_list = [board_cards]
                else:
                    card_list = board_cards

                for card_str in card_list:
                    if not card_str or card_str == '':
                        continue
                    try:
                        converted = self._convert_card(card_str)
                        cards.append(Card.from_string(converted))
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Invalid card in board: {card_str} - {e}")

        return cards

    def _extract_final_pot(self, events: list[dict[str, Any]]) -> int:
        """Extract final pot size from events.

        Args:
            events: List of event dictionaries

        Returns:
            Final pot size
        """
        pot = 0
        for event in events:
            if "Pot" in event and event["Pot"]:
                pot = event["Pot"]
        return pot

    def _find_winner(self, hand_data: dict[str, Any]) -> str | None:
        """Find winner from hand data.

        Args:
            hand_data: Hand dictionary

        Returns:
            Winner name or None
        """
        # Look for player with highest CumulativeWinningsAmt in this hand
        max_winnings = 0
        winner = None

        for player in hand_data.get("Players", []):
            # Calculate winnings this hand
            start_stack = player.get("StartStackAmt", 0)
            end_stack = player.get("EndStackAmt", 0)
            winnings = end_stack - start_stack

            if winnings > max_winnings:
                max_winnings = winnings
                winner = player.get("Name")

        return winner

    def _get_hand_rank(self, rank_value: int) -> HandRank:
        """Convert phevaluator rank value to HandRank enum.

        Args:
            rank_value: phevaluator rank (1 = best, 7462 = worst)

        Returns:
            HandRank enum value
        """
        for min_val, max_val, hand_rank in self.RANK_THRESHOLDS:
            if min_val <= rank_value <= max_val:
                return hand_rank
        return HandRank.HIGH_CARD

    def parse_session_metadata(self, data: dict[str, Any]) -> ParsedSession:
        """Parse full session metadata.

        Args:
            data: Session JSON data

        Returns:
            ParsedSession with all metadata
        """
        session_id = data.get("ID", 0)
        created_at = self._parse_datetime(data.get("CreatedDateTimeUTC", ""))
        software_version = data.get("SoftwareVersion", "")
        table_type = data.get("Type", "")
        event_title = data.get("EventTitle", "")

        parsed_hands: list[ParsedHand] = []
        for hand_data in data.get("Hands", []):
            parsed_hand = ParsedHand(
                hand_num=hand_data.get("HandNum", 0),
                game_variant=hand_data.get("GameVariant", "HOLDEM"),
                duration_seconds=self._parse_duration(hand_data.get("Duration", "")),
                start_time=self._parse_datetime(hand_data.get("StartDateTimeUTC", ""))
                or datetime.now(),
                players=[
                    PlayerInfo.from_dict(p) for p in hand_data.get("Players", [])
                ],
                community_cards=self._extract_community_cards(
                    hand_data.get("Events", [])
                ),
                events=hand_data.get("Events", []),
                pot_size=self._extract_final_pot(hand_data.get("Events", [])),
                winner=self._find_winner(hand_data),
            )
            parsed_hands.append(parsed_hand)

        return ParsedSession(
            session_id=session_id,
            created_at=created_at or datetime.now(),
            software_version=software_version,
            table_type=table_type,
            event_title=event_title,
            hands=parsed_hands,
        )
