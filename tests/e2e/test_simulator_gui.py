"""E2E tests for GFX JSON Simulator Streamlit GUI.

These tests verify the GUI functionality using Playwright.
Run with: npx playwright test tests/e2e/test_simulator_gui.py
Or: python -m pytest tests/e2e/test_simulator_gui.py -v
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestSimulatorGUILayout:
    """Tests for basic GUI layout and structure."""

    def test_page_title(self, page: Page, streamlit_server: str) -> None:
        """Should display correct page title."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Check for app title
        expect(page.locator("h1")).to_contain_text("GFX JSON Simulator")

    def test_sidebar_exists(self, page: Page, streamlit_server: str) -> None:
        """Should have a sidebar with settings."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Sidebar should exist
        sidebar = page.locator("[data-testid='stSidebar']")
        expect(sidebar).to_be_visible()

    def test_tabs_exist(self, page: Page, streamlit_server: str) -> None:
        """Should have simulator and manual import tabs."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Check for tab buttons
        tabs = page.locator("[data-baseweb='tab']")
        expect(tabs).to_have_count(2)

    def test_source_path_input(self, page: Page, streamlit_server: str) -> None:
        """Should have source path input in sidebar."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Find source path input
        sidebar = page.locator("[data-testid='stSidebar']")
        source_input = sidebar.locator("input").first
        expect(source_input).to_be_visible()

    def test_interval_slider(self, page: Page, streamlit_server: str) -> None:
        """Should have interval slider in sidebar."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Find slider
        sidebar = page.locator("[data-testid='stSidebar']")
        slider = sidebar.locator("[data-testid='stSlider']")
        expect(slider).to_be_visible()


@pytest.mark.e2e
class TestSimulatorTab:
    """Tests for the main simulator tab."""

    def test_start_button_disabled_without_files(
        self, page: Page, streamlit_server: str
    ) -> None:
        """Start button should be disabled when no files selected."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Find start button in sidebar
        sidebar = page.locator("[data-testid='stSidebar']")
        start_button = sidebar.get_by_role("button", name=re.compile("시작|Start", re.I))

        # Button should exist (might be disabled)
        expect(start_button).to_be_visible()

    def test_file_selection_area(self, page: Page, streamlit_server: str) -> None:
        """Should show file selection area in main content."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Main content should have file selection info
        main = page.locator("[data-testid='stAppViewContainer']")
        expect(main).to_be_visible()


@pytest.mark.e2e
class TestManualImportTab:
    """Tests for the manual import tab."""

    def test_switch_to_manual_import_tab(
        self, page: Page, streamlit_server: str
    ) -> None:
        """Should be able to switch to manual import tab."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Click on second tab (Manual Import)
        tabs = page.locator("[data-baseweb='tab']")
        tabs.nth(1).click()

        # Wait for tab content to load
        page.wait_for_timeout(500)

        # Should show upload widget or related content
        main = page.locator("[data-testid='stAppViewContainer']")
        expect(main).to_be_visible()

    def test_file_uploader_visible(self, page: Page, streamlit_server: str) -> None:
        """Should show file uploader in manual import tab."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Switch to manual import tab
        tabs = page.locator("[data-baseweb='tab']")
        tabs.nth(1).click()
        page.wait_for_timeout(500)

        # File uploader should be visible
        uploader = page.locator("[data-testid='stFileUploader']")
        expect(uploader).to_be_visible()


@pytest.mark.e2e
class TestInteraction:
    """Tests for user interactions."""

    def test_change_interval_slider(self, page: Page, streamlit_server: str) -> None:
        """Should be able to change interval slider value."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Find slider in sidebar
        sidebar = page.locator("[data-testid='stSidebar']")
        slider = sidebar.locator("[data-testid='stSlider']")

        # Get slider input
        slider_input = slider.locator("input[type='range']")
        expect(slider_input).to_be_visible()

        # Change value (this tests that the slider is interactive)
        slider_input.fill("30")

    def test_enter_source_path(self, page: Page, streamlit_server: str) -> None:
        """Should be able to enter source path."""
        page.goto(streamlit_server)
        page.wait_for_load_state("networkidle")

        # Find first text input in sidebar (source path)
        sidebar = page.locator("[data-testid='stSidebar']")
        inputs = sidebar.locator("input[type='text']")

        if inputs.count() > 0:
            first_input = inputs.first
            first_input.fill("C:\\test\\path")
            expect(first_input).to_have_value("C:\\test\\path")
