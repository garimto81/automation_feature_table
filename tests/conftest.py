"""Global pytest fixtures and configuration."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Create a consistent cv2 mock for all tests
# This prevents inconsistent mock states between test files
import numpy as np

_cv2_mock = MagicMock()
_cv2_mock.VideoCapture = MagicMock()
_cv2_mock.CAP_PROP_BUFFERSIZE = 38
_cv2_mock.CAP_PROP_FRAME_WIDTH = 3
_cv2_mock.CAP_PROP_FRAME_HEIGHT = 4
_cv2_mock.CAP_PROP_FPS = 5
_cv2_mock.IMWRITE_JPEG_QUALITY = 1
_cv2_mock.imencode = MagicMock(
    return_value=(True, np.array([0xFF, 0xD8, 0xFF, 0xE0], dtype=np.uint8))
)
_cv2_mock.resize = MagicMock()

# Set cv2 mock before any test imports
sys.modules["cv2"] = _cv2_mock


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Modify test collection to ensure proper test isolation.

    E2E tests (Playwright) are moved to run LAST to prevent
    event loop contamination affecting other async tests.
    """
    e2e_tests = []
    other_tests = []

    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            e2e_tests.append(item)
        else:
            other_tests.append(item)

    # Reorder: run unit tests first, then E2E tests
    items[:] = other_tests + e2e_tests
