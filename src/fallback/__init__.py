"""Fallback module for Plan B manual marking."""

from src.fallback.detector import AutomationState, FailureDetector, FailureReason
from src.fallback.manual_marker import ManualMarker, MarkType, MultiTableManualMarker, PairedMark

__all__ = [
    "AutomationState",
    "FailureDetector",
    "FailureReason",
    "ManualMarker",
    "MarkType",
    "MultiTableManualMarker",
    "PairedMark",
]
