"""Tests for file_browser module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.simulator.gui.file_browser import (
    format_file_display,
    is_tkinter_available,
    scan_json_files,
)


class TestIsTkinterAvailable:
    """Tests for is_tkinter_available function."""

    def test_returns_bool(self) -> None:
        """Should return a boolean value."""
        result = is_tkinter_available()
        assert isinstance(result, bool)


class TestScanJsonFiles:
    """Tests for scan_json_files function."""

    def test_scan_empty_folder(self, tmp_path: Path) -> None:
        """Should return empty list for empty folder."""
        result = scan_json_files(tmp_path)
        assert result == []

    def test_scan_nonexistent_folder(self, tmp_path: Path) -> None:
        """Should return empty list for non-existent folder."""
        nonexistent = tmp_path / "does_not_exist"
        result = scan_json_files(nonexistent)
        assert result == []

    def test_scan_single_json_file(self, tmp_path: Path) -> None:
        """Should find single JSON file."""
        json_data = {"Hands": [{"HandNum": 1}, {"HandNum": 2}]}
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(json_data), encoding="utf-8")

        result = scan_json_files(tmp_path)

        assert len(result) == 1
        assert result[0]["name"] == "test.json"
        assert result[0]["hand_count"] == 2
        assert result[0]["table"] == ""
        assert result[0]["path"] == str(json_path)

    def test_scan_nested_json_files(self, tmp_path: Path) -> None:
        """Should find nested JSON files with table name."""
        table_a = tmp_path / "TableA"
        table_a.mkdir()
        table_b = tmp_path / "TableB"
        table_b.mkdir()

        # Create JSON files
        json_a = {"Hands": [{"HandNum": 1}]}
        (table_a / "session1.json").write_text(
            json.dumps(json_a), encoding="utf-8"
        )

        json_b = {"Hands": [{"HandNum": 1}, {"HandNum": 2}, {"HandNum": 3}]}
        (table_b / "session1.json").write_text(
            json.dumps(json_b), encoding="utf-8"
        )

        result = scan_json_files(tmp_path)

        assert len(result) == 2
        # Sorted by table name
        assert result[0]["table"] == "TableA"
        assert result[0]["hand_count"] == 1
        assert result[1]["table"] == "TableB"
        assert result[1]["hand_count"] == 3

    def test_scan_skip_invalid_json(self, tmp_path: Path) -> None:
        """Should skip files that cannot be parsed."""
        # Valid JSON
        valid_data = {"Hands": [{"HandNum": 1}]}
        (tmp_path / "valid.json").write_text(
            json.dumps(valid_data), encoding="utf-8"
        )

        # Invalid JSON
        (tmp_path / "invalid.json").write_text("not valid json {", encoding="utf-8")

        result = scan_json_files(tmp_path)

        assert len(result) == 1
        assert result[0]["name"] == "valid.json"

    def test_scan_file_size(self, tmp_path: Path) -> None:
        """Should calculate file size in KB."""
        # Create a file with known content
        json_data = {"Hands": [{"HandNum": i} for i in range(100)]}
        json_path = tmp_path / "large.json"
        json_path.write_text(json.dumps(json_data), encoding="utf-8")

        result = scan_json_files(tmp_path)

        assert len(result) == 1
        assert result[0]["size_kb"] > 0
        # Verify it's a reasonable value
        actual_size_kb = json_path.stat().st_size / 1024
        assert result[0]["size_kb"] == round(actual_size_kb, 1)

    def test_scan_missing_hands_key(self, tmp_path: Path) -> None:
        """Should handle JSON without Hands key."""
        json_data = {"EventTitle": "Test"}
        (tmp_path / "no_hands.json").write_text(
            json.dumps(json_data), encoding="utf-8"
        )

        result = scan_json_files(tmp_path)

        assert len(result) == 1
        assert result[0]["hand_count"] == 0

    def test_scan_sort_order(self, tmp_path: Path) -> None:
        """Should sort by table name, then by file name."""
        # Create in reverse order
        table_z = tmp_path / "TableZ"
        table_z.mkdir()
        table_a = tmp_path / "TableA"
        table_a.mkdir()

        json_data = {"Hands": []}
        (table_z / "b.json").write_text(json.dumps(json_data), encoding="utf-8")
        (table_z / "a.json").write_text(json.dumps(json_data), encoding="utf-8")
        (table_a / "c.json").write_text(json.dumps(json_data), encoding="utf-8")

        result = scan_json_files(tmp_path)

        assert len(result) == 3
        assert result[0]["table"] == "TableA"
        assert result[0]["name"] == "c.json"
        assert result[1]["table"] == "TableZ"
        assert result[1]["name"] == "a.json"
        assert result[2]["table"] == "TableZ"
        assert result[2]["name"] == "b.json"


class TestFormatFileDisplay:
    """Tests for format_file_display function."""

    def test_format_with_table(self) -> None:
        """Should format file info with table name."""
        file_info = {
            "table": "TableA",
            "name": "session1.json",
            "hand_count": 10,
            "size_kb": 5.5,
        }

        result = format_file_display(file_info)

        assert result == "[TableA] session1.json (10 hands, 5.5KB)"

    def test_format_without_table(self) -> None:
        """Should format file info without table name."""
        file_info = {
            "table": "",
            "name": "test.json",
            "hand_count": 3,
            "size_kb": 1.2,
        }

        result = format_file_display(file_info)

        assert result == "test.json (3 hands, 1.2KB)"

    def test_format_zero_hands(self) -> None:
        """Should handle zero hands."""
        file_info = {
            "table": "TableX",
            "name": "empty.json",
            "hand_count": 0,
            "size_kb": 0.1,
        }

        result = format_file_display(file_info)

        assert result == "[TableX] empty.json (0 hands, 0.1KB)"
