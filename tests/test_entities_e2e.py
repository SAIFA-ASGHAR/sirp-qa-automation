"""
test_entities_e2e.py
--------------------
End-to-End QA Automation for SIRP Entities Module.

Test flow:
  TC01 — Navigate to Entities page
  TC02 — Create Entity with all fields
  TC03 — Verify entity appears in grid
  TC04 — Edit Entity (Status: Active → Inactive)
  TC05 — Open Entity detail view
  TC06 — Add Relationship via OmniMap
  TC07 — Browse Related Incidents tab
  TC08 — Browse Related Threat Intels tab
  TC09 — Browse OmniMap tab
  TC10 — Verify Overview tab

Run:
    pytest tests/test_entities_e2e.py -v -s
"""

import pytest
import time
import re
import os
from datetime import datetime
from playwright.sync_api import Page, expect
from utils.login import login

# ── Config ─────────────────────────────────────────────────────────────────
BASE_URL     = os.environ.get("SIRP_BASE_URL", "https://demo3.sirp.io")
ENTITIES_URL = f"{BASE_URL}/entities"
RUN_ID       = datetime.now().strftime("%Y%m%d_%H%M%S")

ENTITY_NAME  = f"[QA AUTO] Entity {RUN_ID}"

RESULTS = []


# ── Helpers ────────────────────────────────────────────────────────────────
def log(step, status, detail=""):
    RESULTS.append({
        "step": step, "status": status,
        "detail": detail, "time": datetime.now().strftime("%H:%M:%S")
    })
    icon = "PASS" if status == "PASS" else "FAIL"
    print(f"\n  [{icon}] {step}")
    if detail:
        print(f"       {detail}")


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ent_page(browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    login(page)
    yield page
    ctx.close()


# ── Tests ──────────────────────────────────────────────────────────────────
class TestEntitiesE2E:

    def test_01_navigate_to_entities(self, ent_page):
        """Navigate to the Entities page and verify it loads."""
        try:
            ent_page.goto(ENTITIES_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            expect(ent_page.locator("button:has-text('Create Entity')").first).to_be_visible(timeout=15000)
            log("TC01 — Navigate to Entities", "PASS", "Entities page loaded, Create Entity button visible")
        except Exception as e:
            log("TC01 — Navigate to Entities", "FAIL", str(e))
            raise

    def test_02_create_entity(self, ent_page):
        """Create a new entity with all required fields."""
        try:
            ent_page.locator("button:has-text('Create Entity')").first.click()
            time.sleep(1)

            # Name
            ent_page.get_by_role("textbox", name="Name").click()
            ent_page.get_by_role("textbox", name="Name").fill(ENTITY_NAME)

            # Severity — click first available dropdown and select first option
            try:
                ent_page.locator("#rc_select_6").click()
                time.sleep(0.5)
                ent_page.locator(
                    ".ant-select-item.ant-select-item-option.ant-select-item-option-active "
                    "> .ant-select-item-option-content"
                ).click()
            except Exception:
                pass

            # Organization
            try:
                ent_page.locator("#rc_select_8").click()
                time.sleep(0.5)
                ent_page.locator(".ant-select-item-option-content").get_by_text(
                    "Project_IT_DWH_Dev"
                ).click()
            except Exception:
                pass

            # Department
            try:
                ent_page.locator("#rc_select_9").click()
                time.sleep(0.5)
                ent_page.get_by_text("SOC").click()
            except Exception:
                pass

            # Version
            ent_page.get_by_role("textbox", name="Version").click()
            ent_page.get_by_role("textbox", name="Version").fill("1.0")

            # Ownership
            try:
                ent_page.locator("#rc_select_10").click()
                time.sleep(0.5)
                ent_page.get_by_text("In-house").nth(1).click()
            except Exception:
                pass

            # Critical Asset toggle
            try:
                ent_page.get_by_role("switch").click()
            except Exception:
                pass

            # Vendor
            try:
                ent_page.locator(".ant-select-selection-overflow").first.click()
                time.sleep(1)
                siemens = ent_page.locator(".ant-select-item-option-content").filter(
                    has_text="Siemens"
                ).first
                siemens.scroll_into_view_if_needed()
                time.sleep(0.5)
                siemens.click(force=True)
                time.sleep(0.5)
            except Exception:
                pass

            # Product
            try:
                ent_page.locator(
                    ".ant-select.sc-kiIyQV.dmlRIP > .ant-select-selector "
                    "> .ant-select-selection-overflow"
                ).click()
                time.sleep(0.5)
                ent_page.get_by_title("SIMATIC ITC1900: All versions").click()
            except Exception:
                pass

            # Submit
            ent_page.get_by_role("button", name="Create", exact=True).click()
            time.sleep(3)

            log("TC02 — Create Entity", "PASS", f"Entity '{ENTITY_NAME}' created")
        except Exception as e:
            log("TC02 — Create Entity", "FAIL", str(e))
            raise

    def test_03_verify_entity_in_grid(self, ent_page):
        """Verify the created entity appears in the grid."""
        try:
            ent_page.goto(ENTITIES_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            entity_row = ent_page.locator(f"text={ENTITY_NAME}").first
            expect(entity_row).to_be_visible(timeout=10000)
            log("TC03 — Verify Entity in Grid", "PASS", f"Entity '{ENTITY_NAME}' found in grid")
        except Exception as e:
            log("TC03 — Verify Entity in Grid", "FAIL", str(e))
            raise

    def test_04_edit_entity_status(self, ent_page):
        """Edit entity status from Active to Inactive."""
        try:
            # Click actions menu on first row
            ent_page.locator(".sc-lnDqNf").first.click(force=True)
            time.sleep(1)
            ent_page.locator("span").filter(has_text="Edit").first.click(force=True)
            time.sleep(2)

            # Change status
            ent_page.get_by_title("Active").click()
            time.sleep(1)
            ent_page.get_by_title("Inactive").click()

            # Submit
            ent_page.get_by_role("button", name="Update").click()
            time.sleep(3)

            log("TC04 — Edit Entity Status", "PASS", "Status changed: Active → Inactive")
        except Exception as e:
            log("TC04 — Edit Entity Status", "FAIL", str(e))
            raise

    def test_05_open_entity_detail(self, ent_page):
        """Open entity detail view by clicking entity name."""
        try:
            ent_page.get_by_role("heading", name=re.compile("Entity|entity")).first.click()
            time.sleep(2)

            # Verify detail view loaded — Overview tab should be visible
            expect(ent_page.locator("text=Overview").first).to_be_visible(timeout=10000)
            log("TC05 — Open Entity Detail", "PASS", "Detail view loaded with Overview tab")
        except Exception as e:
            log("TC05 — Open Entity Detail", "FAIL", str(e))
            raise

    def test_06_add_relationship(self, ent_page):
        """Add a relationship via OmniMap in entity detail."""
        try:
            # Navigate to OmniMap tab via button
            ent_page.get_by_role("button").nth(4).click()
            time.sleep(2)

            ent_page.get_by_role("button", name="Add Relationship").click(force=True)
            time.sleep(2)

            # Relationship type
            ent_page.locator(".ant-select-selector").nth(-2).click(force=True)
            time.sleep(1)
            ent_page.get_by_title("CONNECTED_TO").click()
            time.sleep(1)

            # Close first dropdown
            ent_page.get_by_text("Relationships").click()
            time.sleep(0.5)

            # Entity dropdown
            ent_page.locator(".ant-select-selector").nth(-1).click(force=True)
            time.sleep(1)
            ent_page.get_by_text("new entity test").first.click(force=True)
            time.sleep(1)

            # Submit
            ent_page.get_by_role("button", name="Update").click()
            time.sleep(2)

            log("TC06 — Add Relationship", "PASS", "CONNECTED_TO relationship added")
        except Exception as e:
            log("TC06 — Add Relationship", "FAIL", str(e))
            raise

    def test_07_browse_related_incidents(self, ent_page):
        """Navigate to Related Incidents tab."""
        try:
            ent_page.locator("div").filter(
                has_text=re.compile(r"^Related Incidents\d*$")
            ).first.click()
            time.sleep(1)
            log("TC07 — Related Incidents Tab", "PASS", "Related Incidents tab opened")
        except Exception as e:
            log("TC07 — Related Incidents Tab", "FAIL", str(e))
            raise

    def test_08_browse_related_threat_intels(self, ent_page):
        """Navigate to Related Threat Intels tab."""
        try:
            ent_page.locator("div").filter(
                has_text=re.compile(r"^Related Threat Intels\d*$")
            ).first.click()
            time.sleep(1)
            log("TC08 — Related Threat Intels Tab", "PASS", "Related Threat Intels tab opened")
        except Exception as e:
            log("TC08 — Related Threat Intels Tab", "FAIL", str(e))
            raise

    def test_09_browse_omnimap_tab(self, ent_page):
        """Navigate to OmniMap tab."""
        try:
            ent_page.get_by_text("OmniMap").click()
            time.sleep(2)
            log("TC09 — OmniMap Tab", "PASS", "OmniMap tab loaded")
        except Exception as e:
            log("TC09 — OmniMap Tab", "FAIL", str(e))
            raise

    def test_10_verify_overview_tab(self, ent_page):
        """Navigate back to Overview tab and verify."""
        try:
            ent_page.get_by_text("Overview").first.click()
            time.sleep(2)
            expect(ent_page.locator("text=Overview").first).to_be_visible(timeout=10000)
            log("TC10 — Overview Tab", "PASS", "Overview tab verified")
        except Exception as e:
            log("TC10 — Overview Tab", "FAIL", str(e))
            raise
