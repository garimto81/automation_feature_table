"""Clip marker generation for video editing software."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config.settings import OutputSettings
from src.models.hand import FusedHandResult

logger = logging.getLogger(__name__)


@dataclass
class ClipMarker:
    """Represents a clip marker for video editing."""

    table_id: str
    hand_number: int
    hand_rank: str
    is_premium: bool
    start_time: datetime
    end_time: Optional[datetime] = None
    notes: str = ""

    @property
    def duration(self) -> Optional[timedelta]:
        """Get clip duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "table_id": self.table_id,
            "hand_number": self.hand_number,
            "hand_rank": self.hand_rank,
            "is_premium": self.is_premium,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_sec": self.duration.total_seconds() if self.duration else None,
            "notes": self.notes,
        }


@dataclass
class ClipMarkerManager:
    """Manages clip markers for video editing export."""

    settings: OutputSettings
    markers: list[ClipMarker] = field(default_factory=list)
    _active_hands: dict[str, ClipMarker] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure output directory exists."""
        Path(self.settings.clip_markers_path).mkdir(parents=True, exist_ok=True)

    def start_hand(
        self,
        table_id: str,
        hand_number: int,
        timestamp: datetime,
    ) -> ClipMarker:
        """Mark the start of a hand."""
        marker = ClipMarker(
            table_id=table_id,
            hand_number=hand_number,
            hand_rank="Unknown",
            is_premium=False,
            start_time=timestamp,
        )

        self._active_hands[table_id] = marker
        logger.debug(f"Started hand marker: {table_id} #{hand_number}")

        return marker

    def end_hand(
        self,
        table_id: str,
        result: FusedHandResult,
    ) -> Optional[ClipMarker]:
        """Mark the end of a hand with classification result."""
        if table_id not in self._active_hands:
            # Create marker if not started
            marker = ClipMarker(
                table_id=table_id,
                hand_number=result.hand_number,
                hand_rank=result.rank_name,
                is_premium=result.is_premium,
                start_time=result.timestamp - timedelta(seconds=30),  # Estimate
                end_time=result.timestamp,
            )
        else:
            marker = self._active_hands.pop(table_id)
            marker.hand_rank = result.rank_name
            marker.is_premium = result.is_premium
            marker.end_time = result.timestamp

        self.markers.append(marker)

        if marker.is_premium:
            logger.info(
                f"Premium hand marked: {table_id} #{marker.hand_number} - "
                f"{marker.hand_rank}"
            )

        return marker

    def add_from_result(self, result: FusedHandResult) -> ClipMarker:
        """Add marker directly from a FusedHandResult."""
        marker = ClipMarker(
            table_id=result.table_id,
            hand_number=result.hand_number,
            hand_rank=result.rank_name,
            is_premium=result.is_premium,
            start_time=result.timestamp - timedelta(seconds=30),  # Estimate start
            end_time=result.timestamp,
            notes=f"Source: {result.source.value}, Validated: {result.cross_validated}",
        )

        self.markers.append(marker)
        return marker

    def get_premium_markers(self) -> list[ClipMarker]:
        """Get only premium hand markers."""
        return [m for m in self.markers if m.is_premium]

    def export_json(self, filename: Optional[str] = None) -> Path:
        """Export markers to JSON format."""
        if not filename:
            filename = f"markers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = Path(self.settings.clip_markers_path) / filename

        data = {
            "generated_at": datetime.now().isoformat(),
            "total_markers": len(self.markers),
            "premium_markers": len(self.get_premium_markers()),
            "markers": [m.to_dict() for m in self.markers],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(self.markers)} markers to {output_path}")
        return output_path

    def export_edl(self, filename: Optional[str] = None) -> Path:
        """
        Export markers to EDL (Edit Decision List) format.

        CMX3600 format compatible with DaVinci Resolve, Premiere Pro, etc.
        """
        if not filename:
            filename = f"markers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.edl"

        output_path = Path(self.settings.clip_markers_path) / filename

        lines = [
            "TITLE: Poker Hand Markers",
            f"FCM: NON-DROP FRAME",
            "",
        ]

        for i, marker in enumerate(self.markers, 1):
            if not marker.end_time:
                continue

            # Convert to timecode (assuming 30fps)
            start_tc = self._datetime_to_timecode(marker.start_time)
            end_tc = self._datetime_to_timecode(marker.end_time)

            # EDL event line
            event_num = f"{i:03d}"
            reel = "AX"  # Aux reel
            track = "V"  # Video track
            trans = "C"  # Cut transition

            lines.append(
                f"{event_num}  {reel}       {track}     {trans}        "
                f"{start_tc} {end_tc} {start_tc} {end_tc}"
            )

            # Add comment with hand info
            lines.append(
                f"* FROM CLIP NAME: {marker.table_id} Hand #{marker.hand_number}"
            )
            lines.append(f"* COMMENT: {marker.hand_rank}")

            if marker.is_premium:
                lines.append("* MARKER: PREMIUM HAND")

            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Exported EDL to {output_path}")
        return output_path

    def export_fcpxml(self, filename: Optional[str] = None) -> Path:
        """Export markers to Final Cut Pro XML format."""
        if not filename:
            filename = f"markers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.fcpxml"

        output_path = Path(self.settings.clip_markers_path) / filename

        # Basic FCPXML structure
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
    <resources>
        <format id="r1" name="FFVideoFormat1080p30"/>
    </resources>
    <library>
        <event name="Poker Hand Markers">
            <project name="Hand Markers">
                <sequence format="r1">
                    <spine>
"""

        for i, marker in enumerate(self.markers):
            if not marker.end_time:
                continue

            duration = marker.duration.total_seconds() if marker.duration else 5
            offset = i * duration  # Simple sequential placement

            xml_content += f"""
                        <marker start="{offset}s" duration="{duration}s" value="{marker.hand_rank}">
                            <note>{marker.table_id} Hand #{marker.hand_number}</note>
                        </marker>
"""

        xml_content += """
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_content)

        logger.info(f"Exported FCPXML to {output_path}")
        return output_path

    def _datetime_to_timecode(self, dt: datetime, fps: int = 30) -> str:
        """Convert datetime to SMPTE timecode string."""
        # Use time of day as timecode
        total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        frames = int(dt.microsecond / (1000000 / fps))

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

    def clear(self) -> None:
        """Clear all markers."""
        self.markers.clear()
        self._active_hands.clear()
