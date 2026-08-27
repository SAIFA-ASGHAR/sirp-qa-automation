"""
SIRP Site Crawler
-----------------
Logs into SIRP, crawls every page/link it can find,
and returns a structured map of discovered pages with
their page title, URL, and visible interactive elements.

Usage:
    from utils.crawler import SIRPCrawler

    crawler = SIRPCrawler()
    site_map = crawler.crawl()
    # site_map is a list of PageInfo dicts
"""

from playwright.sync_api import sync_playwright, Page
from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import re
import time


BASE_URL   = "https://demo3.sirp.io"
LOGIN_URL  = f"{BASE_URL}/login"
EMAIL      = "saifa@sirp.io"
PASSWORD   = "S@1f@s1rp"

# Pages we never want to crawl (logout, external links, etc.)
SKIP_PATTERNS = [
    "/logout", "/signout", "mailto:", "tel:", "javascript:",
    "/#", ".pdf", ".zip", ".png", ".jpg",
]

# Known SIRP nav links to make sure we always hit the major sections
SEED_PATHS = [
    "/dashboard",
    "/incidentManagement/All",
    "/incidentManagement/Alerts",
    "/artifacts",
    "/playbooks",
    "/reports",
    "/settings",
    "/admin",
    "/users",
    "/integrations",
]


@dataclass
class PageInfo:
    url: str
    title: str
    section: str                      # e.g. "incidentManagement", "settings"
    buttons: list  = field(default_factory=list)   # visible button labels
    tabs: list     = field(default_factory=list)   # visible tab labels
    forms: list    = field(default_factory=list)   # input placeholders found
    links_found: list = field(default_factory=list)  # hrefs discovered on this page
    error: Optional[str] = None


class SIRPCrawler:
    def __init__(self, headless: bool = True, max_pages: int = 50):
        self.headless   = headless
        self.max_pages  = max_pages
        self.visited    = set()
        self.queue      = []
        self.site_map   = []

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #

    def crawl(self) -> list:
        """
        Main entry point. Returns a list of PageInfo dicts.
        """
        print(f"\n{'='*55}")
        print("  SIRP Crawler starting...")
        print(f"{'='*55}\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page    = context.new_page()

            # ── 1. Login ──────────────────────────────────────────────
            self._login(page)

            # ── 2. Seed the queue with known nav links ────────────────
            for path in SEED_PATHS:
                self._enqueue(BASE_URL + path)

            # ── 3. Crawl until queue is empty or limit reached ────────
            while self.queue and len(self.visited) < self.max_pages:
                url = self.queue.pop(0)
                if url in self.visited:
                    continue

                info = self._visit_page(page, url)
                if info:
                    self.site_map.append(asdict(info))
                    # Enqueue any new links found on this page
                    for link in info.links_found:
                        self._enqueue(link)

            browser.close()

        print(f"\n{'='*55}")
        print(f"  Crawl complete! {len(self.site_map)} pages discovered.")
        print(f"{'='*55}\n")
        return self.site_map

    def save_site_map(self, path: str = "site_map.json"):
        """Save the crawl results to a JSON file."""
        with open(path, "w") as f:
            json.dump(self.site_map, f, indent=2)
        print(f"Site map saved to {path}")

    # ------------------------------------------------------------------ #
    #  Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _login(self, page: Page):
        print("  Logging in...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.get_by_placeholder("Email").fill(EMAIL)
        page.get_by_placeholder("Password").fill(PASSWORD)
        page.get_by_role("button", name="Login").click()
        page.wait_for_url("**/dashboard", timeout=15000)
        print("  Login successful!\n")

    def _enqueue(self, url: str):
        """Add a URL to the queue if it's valid and not yet seen."""
        if not url:
            return
        # Normalise — strip fragments and trailing slashes
        url = url.split("#")[0].rstrip("/")
        if not url.startswith(BASE_URL):
            return
        if url in self.visited:
            return
        if any(skip in url for skip in SKIP_PATTERNS):
            return
        if url not in self.queue:
            self.queue.append(url)

    def _visit_page(self, page: Page, url: str) -> Optional[PageInfo]:
        self.visited.add(url)
        section = self._extract_section(url)
        print(f"  [{len(self.visited):02d}] Visiting: {url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(1.2)   # let React render

            title   = self._get_title(page)
            buttons = self._get_buttons(page)
            tabs    = self._get_tabs(page)
            forms   = self._get_form_inputs(page)
            links   = self._collect_links(page)

            info = PageInfo(
                url=url,
                title=title,
                section=section,
                buttons=buttons,
                tabs=tabs,
                forms=forms,
                links_found=links,
            )
            print(f"       title={title!r}  buttons={len(buttons)}  tabs={len(tabs)}  links={len(links)}")
            return info

        except Exception as e:
            print(f"       ERROR: {e}")
            return PageInfo(url=url, title="", section=section, error=str(e))

    def _get_title(self, page: Page) -> str:
        try:
            # Try h1 first, then page title
            h1 = page.locator("h1").first
            if h1.is_visible():
                return h1.inner_text().strip()
        except Exception:
            pass
        return page.title().strip()

    def _get_buttons(self, page: Page) -> list:
        try:
            btns = page.get_by_role("button").all()
            labels = []
            for b in btns[:20]:   # cap at 20
                try:
                    txt = b.inner_text().strip()
                    if txt and len(txt) < 60:
                        labels.append(txt)
                except Exception:
                    pass
            return list(dict.fromkeys(labels))   # deduplicate, preserve order
        except Exception:
            return []

    def _get_tabs(self, page: Page) -> list:
        try:
            tabs = page.get_by_role("tab").all()
            return [t.inner_text().strip() for t in tabs if t.inner_text().strip()]
        except Exception:
            return []

    def _get_form_inputs(self, page: Page) -> list:
        try:
            inputs = page.locator("input[placeholder], textarea[placeholder]").all()
            return list({i.get_attribute("placeholder") for i in inputs if i.get_attribute("placeholder")})
        except Exception:
            return []

    def _collect_links(self, page: Page) -> list:
        """Collect all internal hrefs from <a> tags on the current page."""
        try:
            anchors = page.locator("a[href]").all()
            links = []
            for a in anchors[:80]:  # cap per-page
                try:
                    href = a.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = BASE_URL + href
                    if href.startswith(BASE_URL):
                        links.append(href.split("#")[0])
                except Exception:
                    pass
            return list(set(links))
        except Exception:
            return []

    def _extract_section(self, url: str) -> str:
        path = url.replace(BASE_URL, "").strip("/")
        return path.split("/")[0] if path else "root"
