"""Data models for poker hand processing."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SourceType(Enum):
    """Source of hand detection result."""

    PRIMARY = "pokergfx"
    SECONDARY = "ai_video"
    FUSED = "fused"
    MANUAL = "manual"


class HandRank(Enum):
    """Poker hand rankings from strongest to weakest."""

    ROYAL_FLUSH = 1
    STRAIGHT_FLUSH = 2
    FOUR_OF_A_KIND = 3
    FULL_HOUSE = 4
    FLUSH = 5
    STRAIGHT = 6
    THREE_OF_A_KIND = 7
    TWO_PAIR = 8
    ONE_PAIR = 9
    HIGH_CARD = 10

    @property
    def display_name(self) -> str:
        """Return human-readable name."""
        return self.name.replace("_", " ").title()

    @property
    def is_premium(self) -> bool:
        """Check if this is a premium hand (Full House or better)."""
        return self.value <= 4


@dataclass
class Card:
    """Represents a playing card."""

    rank: str  # 2-9, T, J, Q, K, A
    suit: str  # h, d, c, s (hearts, diamonds, clubs, spades)

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @classmethod
    def from_string(cls, card_str: str) -> "Card":
        """Parse card from string like 'Ah', 'Kd', '10s'."""
        if len(card_str) == 2:
            return cls(rank=card_str[0], suit=card_str[1].lower())
        elif len(card_str) == 3:  # '10h' format
            return cls(rank=card_str[:2], suit=card_str[2].lower())
        raise ValueError(f"Invalid card string: {card_str}")


@dataclass
class PlayerInfo:
    """Player information in a hand."""

    seat: int
    name: str
    hole_cards: list[Card] = field(default_factory=list)
    stack: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PlayerInfo":
        """Create from dictionary.

        Supports both standard format (seat, name, hole_cards, stack)
        and PRD-0002 PokerGFX format (PlayerNum, Name, HoleCards, EndStackAmt).
        """
        # Support both key formats
        seat_val = data.get("seat") or data.get("PlayerNum", 0) or 0
        seat = int(seat_val) if isinstance(seat_val, (int, float, str)) else 0
        name = str(data.get("name") or data.get("Name", ""))
        raw_cards = data.get("hole_cards") or data.get("HoleCards", [])
        stack_val = data.get("stack") or data.get("EndStackAmt", 0) or 0
        stack = int(stack_val) if isinstance(stack_val, (int, float, str)) else 0

        if not isinstance(raw_cards, list):
            raw_cards = []
        hole_cards = [Card.from_string(str(c)) for c in raw_cards]
        return cls(
            seat=seat,
            name=name,
            hole_cards=hole_cards,
            stack=stack,
        )


@dataclass
class HandAction:
    """Represents a player action in a hand."""

    player: str
    action: str  # fold, check, call, raise, bet, all-in
    amount: int = 0
    street: str = ""  # preflop, flop, turn, river

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "HandAction":
        """Create from dictionary."""
        amount_val = data.get("amount", 0) or 0
        amount = int(amount_val) if isinstance(amount_val, (int, float, str)) else 0
        return cls(
            player=str(data["player"]),
            action=str(data["action"]),
            amount=amount,
            street=str(data.get("street", "")),
        )


@dataclass
class HandResult:
    """Result from Primary (PokerGFX) processing."""

    table_id: str
    hand_number: int
    hand_rank: HandRank
    rank_value: int  # Raw phevaluator rank value
    is_premium: bool
    confidence: float  # Always 1.0 for RFID data
    players_showdown: list[dict[str, object]]
    pot_size: int
    timestamp: datetime
    community_cards: list[Card] = field(default_factory=list)
    winner: str | None = None

    @property
    def rank_name(self) -> str:
        """Get human-readable rank name."""
        return self.hand_rank.display_name


@dataclass
class AIVideoResult:
    """Result from Secondary (AI Video) processing."""

    table_id: str
    detected_event: str  # hand_start, hand_end, showdown, all_in
    detected_cards: list[Card]
    hand_rank: HandRank | None
    confidence: float  # 0.0 - 1.0
    context: str  # AI-generated game situation description
    timestamp: datetime

    @property
    def rank_name(self) -> str | None:
        """Get human-readable rank name."""
        return self.hand_rank.display_name if self.hand_rank else None


@dataclass
class FusedHandResult:
    """Result from Fusion Engine combining Primary and Secondary."""

    table_id: str
    hand_number: int
    hand_rank: HandRank
    confidence: float
    source: SourceType
    primary_result: HandResult | None
    secondary_result: AIVideoResult | None
    cross_validated: bool
    requires_review: bool
    timestamp: datetime
    community_cards: list[Card] = field(default_factory=list)
    rank_value: int = 0
    pot_size: int = 0
    winner: str | None = None

    @property
    def rank_name(self) -> str:
        """Get human-readable rank name."""
        return self.hand_rank.display_name

    @property
    def is_premium(self) -> bool:
        """Check if this is a premium hand."""
        return self.hand_rank.is_premium
