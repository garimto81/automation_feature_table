"""File browser utilities for Streamlit GUI."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

# Try to import tkinter for file dialogs
_TKINTER_AVAILABLE = False
try:
    import tkinter as tk
    from tkinter import filedialog

    _TKINTER_AVAILABLE = True
except ImportError:
    pass


def is_tkinter_available() -> bool:
    """Check if tkinter is available for file dialogs."""
    return _TKINTER_AVAILABLE


def select_folder(title: str = "Select Folder", initial_dir: str = "") -> str | None:
    """Open folder selection dialog.

    Args:
        title: Dialog title
        initial_dir: Initial directory path

    Returns:
        Selected folder path or None if cancelled
    """
    if not _TKINTER_AVAILABLE:
        return None

    result: list[str | None] = [None]

    def _select() -> None:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder = filedialog.askdirectory(title=title, initialdir=initial_dir or "/")
        result[0] = folder if folder else None
        root.destroy()

    # Run in thread to avoid blocking
    thread = threading.Thread(target=_select)
    thread.start()
    thread.join(timeout=60)  # 60 second timeout

    return result[0]


def select_files(
    title: str = "Select Files",
    initial_dir: str = "",
    filetypes: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Open file selection dialog.

    Args:
        title: Dialog title
        initial_dir: Initial directory path
        filetypes: List of (description, pattern) tuples

    Returns:
        List of selected file paths
    """
    if not _TKINTER_AVAILABLE:
        return []

    if filetypes is None:
        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]

    result: list[list[str]] = [[]]

    def _select() -> None:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        files = filedialog.askopenfilenames(
            title=title,
            initialdir=initial_dir or "/",
            filetypes=filetypes,
        )
        result[0] = list(files) if files else []
        root.destroy()

    thread = threading.Thread(target=_select)
    thread.start()
    thread.join(timeout=60)

    return result[0]


def scan_json_files(folder: Path) -> list[dict[str, Any]]:
    """Scan folder for JSON files and extract metadata.

    Args:
        folder: Folder to scan

    Returns:
        List of file info dicts with path, name, table, hand_count
    """
    if not folder.exists():
        return []

    files = []
    for json_path in folder.rglob("*.json"):
        try:
            # Get relative path for display
            rel_path = json_path.relative_to(folder)
            parts = rel_path.parts

            # Extract table name (first directory)
            table_name = parts[0] if len(parts) > 1 else ""

            # Read and parse to get hand count
            data = json.loads(json_path.read_text(encoding="utf-8"))
            hand_count = len(data.get("Hands", []))

            # Get file size
            size_kb = json_path.stat().st_size / 1024

            files.append(
                {
                    "path": str(json_path),
                    "rel_path": str(rel_path),
                    "name": json_path.name,
                    "table": table_name,
                    "hand_count": hand_count,
                    "size_kb": round(size_kb, 1),
                }
            )
        except Exception:
            # Skip files that can't be parsed
            continue

    # Sort by table name, then by file name
    files.sort(key=lambda x: (x["table"], x["name"]))
    return files


def format_file_display(file_info: dict[str, Any]) -> str:
    """Format file info for display in selectbox.

    Args:
        file_info: File info dict

    Returns:
        Formatted display string
    """
    table = file_info["table"]
    name = file_info["name"]
    hands = file_info["hand_count"]
    size = file_info["size_kb"]

    if table:
        return f"[{table}] {name} ({hands} hands, {size}KB)"
    return f"{name} ({hands} hands, {size}KB)"
