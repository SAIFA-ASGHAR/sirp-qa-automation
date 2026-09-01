"""
conftest.py
-----------
Shared fixtures for SIRP QA test suites.

Provides:
  - Playwright browser fixture (headed mode for debugging, headless for CI)
  - Auto-screenshot on EVERY test (pass and fail)
  - Report generation hook
"""

import pytest, os
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path("reports/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ── Browser fixture ─────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def browser():
    """
    Launch a Playwright Chromium browser for the full test session.
    Set HEADLESS=1 env var for CI; defaults to headed for local debugging.
    """
    headless = os.environ.get("HEADLESS", "0") == "1"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            slow_mo=300,
            args=["--start-maximized"]
        )
        yield browser
        browser.close()


# ── Auto-screenshot on EVERY test (pass and fail) ──────────────────────────
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture a screenshot after every test — pass or fail."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        # Find the page from the test's fixtures
        page = None
        for fixture_name in ["im_page", "sara_page", "auto_page"]:
            if fixture_name in item.funcargs:
                page = item.funcargs[fixture_name]
                break

        if page and not page.is_closed():
            status = "PASS" if report.passed else "FAIL"
            ts = datetime.now().strftime("%H%M%S")
            # Consistent naming: STATUS_testname_timestamp.png
            name = f"{status}_{item.name}_{ts}.png"
            path = SCREENSHOT_DIR / name
            try:
                page.screenshot(path=str(path), full_page=True)
                print(f"\n  Screenshot: {path}")
            except Exception as e:
                print(f"\n  Screenshot failed: {e}")
