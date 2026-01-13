"""Pytest fixtures for Streamlit E2E tests."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture(scope="module")
def streamlit_server() -> Generator[str, None, None]:
    """Start Streamlit server for testing.

    Yields:
        URL of the running Streamlit server
    """
    # Start Streamlit in background
    process = subprocess.Popen(
        [
            "python",
            "-m",
            "streamlit",
            "run",
            "src/simulator/gui/app.py",
            "--server.port=8502",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    url = "http://localhost:8502"
    max_wait = 30
    started = False

    for _ in range(max_wait):
        try:
            import urllib.request

            urllib.request.urlopen(url, timeout=1)
            started = True
            break
        except Exception:
            time.sleep(1)

    if not started:
        process.terminate()
        pytest.skip("Streamlit server failed to start")

    yield url

    # Cleanup
    process.terminate()
    process.wait(timeout=5)


@pytest.fixture
def sample_json_folder(tmp_path: Path) -> Path:
    """Create a temporary folder with sample JSON files.

    Returns:
        Path to the folder containing sample JSON files
    """
    # Create table folders
    table_a = tmp_path / "TableA"
    table_a.mkdir()
    table_b = tmp_path / "TableB"
    table_b.mkdir()

    # Create sample JSON data
    json_a = {
        "CreatedDateTimeUTC": "2025-01-13T10:00:00Z",
        "EventTitle": "Test Event A",
        "Hands": [
            {"HandNum": 1, "Duration": "PT1M10S"},
            {"HandNum": 2, "Duration": "PT1M20S"},
        ],
    }

    json_b = {
        "CreatedDateTimeUTC": "2025-01-13T11:00:00Z",
        "EventTitle": "Test Event B",
        "Hands": [
            {"HandNum": 1, "Duration": "PT2M00S"},
            {"HandNum": 2, "Duration": "PT1M30S"},
            {"HandNum": 3, "Duration": "PT1M45S"},
        ],
    }

    (table_a / "session1.json").write_text(
        json.dumps(json_a, indent=2), encoding="utf-8"
    )
    (table_b / "session1.json").write_text(
        json.dumps(json_b, indent=2), encoding="utf-8"
    )

    return tmp_path
