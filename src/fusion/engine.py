"""Fusion Engine for combining Primary and Secondary results."""

import logging
from collections.abc import Callable
from datetime import datetime

from src.models.hand import (
    AIVideoResult,
    FusedHandResult,
    HandRank,
    HandResult,
    SourceType,
)

logger = logging.getLogger(__name__)


class FusionEngine:
    """
    Fusion Engine for cross-validation and failover logic.

    Decision Matrix:
    - Case 1: Primary Available + Secondary Matches → Use Primary (validated)
    - Case 2: Primary Available + Secondary Differs → Use Primary (flag for review)
    - Case 3: Primary Unavailable + Secondary Available → Use Secondary (if confidence > threshold)
    - Case 4: Both Unavailable → Mark as Undetected
    """

    def __init__(
        self,
        secondary_confidence_threshold: float = 0.80,
        on_result: Callable[[FusedHandResult], None] | None = None,
    ):
        self.secondary_confidence_threshold = secondary_confidence_threshold
        self._on_result = on_result
        self._stats = {
            "total": 0,
            "primary_only": 0,
            "cross_validated": 0,
            "secondary_fallback": 0,
            "undetected": 0,
            "review_flagged": 0,
        }

    def fuse(
        self,
        primary: HandResult | None,
        secondary: AIVideoResult | None,
    ) -> FusedHandResult:
        """
        Fuse Primary and Secondary results.

        Args:
            primary: Result from PokerGFX (if available)
            secondary: Result from AI Video (if available)

        Returns:
            FusedHandResult combining both sources
        """
        self._stats["total"] += 1

        # Case 1 & 2: Primary available
        if primary:
            cross_validated = self._cross_validate(primary, secondary)

            if cross_validated:
                self._stats["cross_validated"] += 1
            else:
                self._stats["primary_only"] += 1
                if secondary is not None:
                    self._stats["review_flagged"] += 1

            result = FusedHandResult(
                table_id=primary.table_id,
                hand_number=primary.hand_number,
                hand_rank=primary.hand_rank,
                confidence=1.0,
                source=SourceType.PRIMARY,
                primary_result=primary,
                secondary_result=secondary,
                cross_validated=cross_validated,
                requires_review=not cross_validated and secondary is not None,
                timestamp=primary.timestamp,
            )

            logger.info(
                f"[FUSED] Hand #{primary.hand_number}: {primary.rank_name} "
                f"(validated: {cross_validated})"
            )

        # Case 3: Primary unavailable, Secondary available
        elif secondary and secondary.confidence >= self.secondary_confidence_threshold:
            self._stats["secondary_fallback"] += 1

            hand_rank = secondary.hand_rank or HandRank.HIGH_CARD

            result = FusedHandResult(
                table_id=secondary.table_id,
                hand_number=-1,  # Unknown from video
                hand_rank=hand_rank,
                confidence=secondary.confidence,
                source=SourceType.SECONDARY,
                primary_result=None,
                secondary_result=secondary,
                cross_validated=False,
                requires_review=True,  # AI results always need review
                timestamp=secondary.timestamp,
            )

            logger.warning(
                f"[FUSED] Using secondary source for {secondary.table_id}: "
                f"{secondary.detected_event} (confidence: {secondary.confidence:.2f})"
            )

        # Case 4: Both unavailable
        else:
            self._stats["undetected"] += 1

            result = FusedHandResult(
                table_id=secondary.table_id if secondary else "unknown",
                hand_number=-1,
                hand_rank=HandRank.HIGH_CARD,
                confidence=0.0,
                source=SourceType.MANUAL,
                primary_result=None,
                secondary_result=secondary,
                cross_validated=False,
                requires_review=True,
                timestamp=datetime.now(),
            )

            logger.warning("[FUSED] No valid source available, manual input required")

        # Call result handler if registered
        if self._on_result:
            try:
                self._on_result(result)
            except Exception as e:
                logger.error(f"Error in result handler: {e}")

        return result

    def _cross_validate(
        self,
        primary: HandResult,
        secondary: AIVideoResult | None,
    ) -> bool:
        """
        Cross-validate Primary and Secondary results.

        Returns True if:
        - Secondary is not available (no conflict)
        - Secondary hand rank matches Primary
        """
        if not secondary:
            return True

        if not secondary.hand_rank:
            return True

        # Compare hand ranks
        if primary.hand_rank == secondary.hand_rank:
            return True

        # Log mismatch for debugging
        logger.debug(
            f"Hand rank mismatch: Primary={primary.hand_rank.display_name}, "
            f"Secondary={secondary.hand_rank.display_name}"
        )

        return False

    def get_stats(self) -> dict:
        """Get fusion statistics."""
        total = self._stats["total"]

        if total == 0:
            return self._stats

        return {
            **self._stats,
            "cross_validation_rate": self._stats["cross_validated"] / total,
            "secondary_fallback_rate": self._stats["secondary_fallback"] / total,
            "undetected_rate": self._stats["undetected"] / total,
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        for key in self._stats:
            self._stats[key] = 0


class MultiTableFusionEngine:
    """Fusion Engine managing multiple tables."""

    def __init__(
        self,
        table_ids: list[str],
        secondary_confidence_threshold: float = 0.80,
    ):
        self.engines: dict[str, FusionEngine] = {}

        for table_id in table_ids:
            self.engines[table_id] = FusionEngine(
                secondary_confidence_threshold=secondary_confidence_threshold
            )

    def fuse(
        self,
        table_id: str,
        primary: HandResult | None,
        secondary: AIVideoResult | None,
    ) -> FusedHandResult:
        """Fuse results for a specific table."""
        if table_id not in self.engines:
            self.engines[table_id] = FusionEngine()

        return self.engines[table_id].fuse(primary, secondary)

    def get_all_stats(self) -> dict[str, dict]:
        """Get statistics for all tables."""
        return {
            table_id: engine.get_stats()
            for table_id, engine in self.engines.items()
        }

    def get_aggregate_stats(self) -> dict:
        """Get aggregated statistics across all tables."""
        aggregate = {
            "total": 0,
            "primary_only": 0,
            "cross_validated": 0,
            "secondary_fallback": 0,
            "undetected": 0,
            "review_flagged": 0,
        }

        for engine in self.engines.values():
            stats = engine.get_stats()
            for key in aggregate:
                aggregate[key] += stats.get(key, 0)

        total = aggregate["total"]
        if total > 0:
            aggregate["cross_validation_rate"] = aggregate["cross_validated"] / total
            aggregate["secondary_fallback_rate"] = aggregate["secondary_fallback"] / total
            aggregate["undetected_rate"] = aggregate["undetected"] / total

        return aggregate
