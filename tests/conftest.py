"""Global pytest fixtures and configuration."""

from __future__ import annotations

import asyncio
from typing import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session.

    This ensures all async tests share the same event loop,
    preventing conflicts with Playwright E2E tests.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


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
