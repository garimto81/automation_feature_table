"""Hand classification using phevaluator."""


from phevaluator import evaluate_cards

from src.models.hand import Card, HandRank


class HandClassifier:
    """Poker hand classifier using phevaluator library."""

    # phevaluator rank ranges to HandRank mapping
    # phevaluator returns lower values for better hands
    RANK_THRESHOLDS = {
        HandRank.ROYAL_FLUSH: (1, 1),
        HandRank.STRAIGHT_FLUSH: (2, 10),
        HandRank.FOUR_OF_A_KIND: (11, 166),
        HandRank.FULL_HOUSE: (167, 322),
        HandRank.FLUSH: (323, 1599),
        HandRank.STRAIGHT: (1600, 1609),
        HandRank.THREE_OF_A_KIND: (1610, 2467),
        HandRank.TWO_PAIR: (2468, 3325),
        HandRank.ONE_PAIR: (3326, 6185),
        HandRank.HIGH_CARD: (6186, 7462),
    }

    # Card rank conversion: phevaluator uses 0-12 (2-A)
    RANK_MAP = {
        "2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5, "8": 6,
        "9": 7, "T": 8, "10": 8, "J": 9, "Q": 10, "K": 11, "A": 12,
    }

    # Suit conversion: phevaluator uses 0-3
    SUIT_MAP = {"c": 0, "d": 1, "h": 2, "s": 3}

    def convert_card(self, card: Card) -> int:
        """Convert Card object to phevaluator integer format."""
        rank_idx = self.RANK_MAP.get(card.rank.upper(), self.RANK_MAP.get(card.rank))
        suit_idx = self.SUIT_MAP.get(card.suit.lower())

        if rank_idx is None or suit_idx is None:
            raise ValueError(f"Invalid card: {card}")

        # phevaluator card format: rank * 4 + suit
        return rank_idx * 4 + suit_idx

    def convert_cards(self, cards: list[Card]) -> list[int]:
        """Convert list of Card objects to phevaluator format."""
        return [self.convert_card(c) for c in cards]

    def evaluate(self, hole_cards: list[Card], community_cards: list[Card]) -> int:
        """
        Evaluate hand strength.

        Args:
            hole_cards: Player's hole cards (2 cards)
            community_cards: Community cards (3-5 cards)

        Returns:
            Raw phevaluator rank value (lower is better)
        """
        all_cards = hole_cards + community_cards

        if len(all_cards) < 5:
            raise ValueError(f"Need at least 5 cards, got {len(all_cards)}")

        card_ints = self.convert_cards(all_cards)

        if len(card_ints) == 5:
            return int(evaluate_cards(*card_ints))
        elif len(card_ints) == 6:
            return int(evaluate_cards(*card_ints))
        elif len(card_ints) == 7:
            return int(evaluate_cards(*card_ints))
        else:
            raise ValueError(f"Invalid number of cards: {len(card_ints)}")

    def get_hand_rank(self, rank_value: int) -> HandRank:
        """Convert phevaluator rank value to HandRank enum."""
        for hand_rank, (min_val, max_val) in self.RANK_THRESHOLDS.items():
            if min_val <= rank_value <= max_val:
                return hand_rank
        return HandRank.HIGH_CARD

    def classify(
        self,
        hole_cards: list[Card],
        community_cards: list[Card],
    ) -> dict[str, object]:
        """
        Classify poker hand.

        Args:
            hole_cards: Player's hole cards
            community_cards: Community cards

        Returns:
            Dictionary with rank_value, hand_rank, rank_name, is_premium
        """
        rank_value = self.evaluate(hole_cards, community_cards)
        hand_rank = self.get_hand_rank(rank_value)

        return {
            "rank_value": rank_value,
            "hand_rank": hand_rank,
            "rank_name": hand_rank.display_name,
            "is_premium": hand_rank.is_premium,
        }

    def compare_hands(
        self,
        hand1: tuple[list[Card], list[Card]],
        hand2: tuple[list[Card], list[Card]],
    ) -> int:
        """
        Compare two hands.

        Args:
            hand1: Tuple of (hole_cards, community_cards) for player 1
            hand2: Tuple of (hole_cards, community_cards) for player 2

        Returns:
            -1 if hand1 wins, 1 if hand2 wins, 0 if tie
        """
        rank1 = self.evaluate(hand1[0], hand1[1])
        rank2 = self.evaluate(hand2[0], hand2[1])

        if rank1 < rank2:
            return -1
        elif rank1 > rank2:
            return 1
        return 0

    def find_best_hand(
        self,
        players: list[dict[str, object]],
        community_cards: list[Card],
    ) -> dict[str, object] | None:
        """
        Find the best hand among players.

        Args:
            players: List of player dicts with 'name' and 'hole_cards'
            community_cards: Community cards

        Returns:
            Dict with winner info or None if no valid hands
        """
        best_player = None
        best_rank = float("inf")

        for player in players:
            hole_cards_obj = player.get("hole_cards")
            if not hole_cards_obj:
                continue

            if not isinstance(hole_cards_obj, list):
                continue

            hole_cards: list[Card] = []
            if hole_cards_obj and isinstance(hole_cards_obj[0], str):
                hole_cards = [Card.from_string(str(c)) for c in hole_cards_obj]
            else:
                hole_cards = list(hole_cards_obj)  # type: ignore[arg-type]

            try:
                rank_value = self.evaluate(hole_cards, community_cards)
                if rank_value < best_rank:
                    best_rank = rank_value
                    best_player = {
                        "name": player["name"],
                        "rank_value": rank_value,
                        "hand_rank": self.get_hand_rank(rank_value),
                        "hole_cards": hole_cards,
                    }
            except ValueError:
                continue

        return best_player
