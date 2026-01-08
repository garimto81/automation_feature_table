"""Hand splitting logic for GFX JSON files."""

from __future__ import annotations

from typing import Any


class HandSplitter:
    """Utility class for splitting and building cumulative hands from GFX JSON."""

    @staticmethod
    def split_hands(json_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract and sort hands from JSON data.

        Args:
            json_data: Parsed JSON data containing 'Hands' array

        Returns:
            List of hand dictionaries sorted by HandNum
        """
        hands = json_data.get("Hands", [])
        return sorted(hands, key=lambda h: h.get("HandNum", 0))

    @staticmethod
    def build_cumulative(
        hands: list[dict[str, Any]],
        count: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Build cumulative JSON with first N hands.

        Args:
            hands: Full list of sorted hands
            count: Number of hands to include (1 to len(hands))
            metadata: Original JSON metadata (CreatedDateTimeUTC, EventTitle, etc.)

        Returns:
            JSON dict with cumulative hands
        """
        return {
            "CreatedDateTimeUTC": metadata.get("CreatedDateTimeUTC", ""),
            "EventTitle": metadata.get("EventTitle", ""),
            "Hands": hands[:count],
        }

    @staticmethod
    def get_hand_count(json_data: dict[str, Any]) -> int:
        """Get total number of hands in JSON data.

        Args:
            json_data: Parsed JSON data

        Returns:
            Number of hands
        """
        return len(json_data.get("Hands", []))

    @staticmethod
    def extract_metadata(json_data: dict[str, Any]) -> dict[str, Any]:
        """Extract metadata from JSON data (everything except Hands).

        Args:
            json_data: Parsed JSON data

        Returns:
            Metadata dictionary
        """
        return {
            "CreatedDateTimeUTC": json_data.get("CreatedDateTimeUTC", ""),
            "EventTitle": json_data.get("EventTitle", ""),
        }
