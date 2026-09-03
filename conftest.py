"""
conftest.py
-----------
Shared fixtures for SIRP QA test suites.

Provides:
  - Playwright browser fixture (headed mode for debugging, headless for CI)
  - Auto-screenshot on test failure
  - Report generation hook for IM E2E suite
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
            slow_mo=300,           # slight delay so you can see actions
            args=["--start-maximized"]
        )
        yield browser
        browser.close()


# ── Auto-screenshot on failure ──────────────────────────────────────────────
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture a screenshot whenever a test fails."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        # Try to find the page from the test's fixtures
        page = None
        for fixture_name in ["im_page", "sara_page", "auto_page", "ent_page"]:
            if fixture_name in item.funcargs:
                page = item.funcargs[fixture_name]
                break

        if page and not page.is_closed():
            status = "PASS" if report.passed else "FAIL"
            ts = datetime.now().strftime("%H%M%S")
            name = f"{status}_{item.name}_{ts}.png"
            path = SCREENSHOT_DIR / name
            try:
                page.screenshot(path=str(path), full_page=True)
                print(f"\n  Screenshot: {path}")
            except Exception as e:
                print(f"\n  Screenshot failed: {e}")


# ── Report generation hook ──────────────────────────────────────────────────
def pytest_sessionfinish(session, exitstatus):
    """
    After all tests finish, generate the HTML report
    by calling the report generator from the IM test module.
    """
    try:
        from test_incident_management_e2e import RESULTS, REPORT_DIR, RUN_ID
        if not RESULTS:
            return
        _generate_im_report(RESULTS, REPORT_DIR, RUN_ID)
    except ImportError:
        pass  # IM tests weren't part of this run


def _generate_im_report(results, report_dir, run_id):
    """Generate the IM E2E HTML report."""
    from datetime import datetime

    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    total  = len(results)
    pct    = round(len(passed) / total * 100) if total else 0
    bar    = "#22c55e" if pct >= 70 else "#f59e0b" if pct >= 50 else "#ef4444"

    rows = ""
    for i, r in enumerate(results, 1):
        c  = "#166534" if r["status"] == "PASS" else "#991b1b"
        bg = "#dcfce7" if r["status"] == "PASS" else "#fee2e2"
        ic = "✅" if r["status"] == "PASS" else "❌"
        rows += f"""<tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:10px 12px;color:#6b7280;font-size:12px;text-align:center;">{i}</td>
          <td style="padding:10px 12px;color:#9ca3af;font-size:12px;">{r['time']}</td>
          <td style="padding:10px 12px;color:#e5e7eb;font-size:13px;font-weight:500;">{r['step']}</td>
          <td style="padding:10px 12px;"><span style="background:{bg};color:{c};padding:3px 12px;border-radius:12px;font-size:12px;font-weight:600;">{ic} {r['status']}</span></td>
          <td style="padding:10px 12px;color:#9ca3af;font-size:12px;">{r['detail']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>SIRP IM E2E — {run_id}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e5e7eb}}
.hdr{{background:linear-gradient(135deg,#1e1b4b,#312e81,#1e40af);padding:40px 48px}}
.hdr-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}}
.logo{{font-size:13px;color:#a5b4fc;letter-spacing:2px;text-transform:uppercase;font-weight:600}}
.rid{{font-size:11px;color:#818cf8;background:rgba(99,102,241,.2);padding:4px 10px;border-radius:8px}}
h1{{font-size:26px;font-weight:700;color:#fff;margin:12px 0 4px}}
.sub{{color:#a5b4fc;font-size:14px}}
.meta{{display:flex;gap:24px;margin-top:16px;flex-wrap:wrap}}
.mi{{font-size:12px;color:#818cf8}}.mi span{{color:#c7d2fe;font-weight:500}}
.content{{padding:32px 48px;max-width:1300px;margin:0 auto}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.metric{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px;text-align:center}}
.mv{{font-size:32px;font-weight:700;margin-bottom:4px}}
.ml{{font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:12px;margin-bottom:24px;overflow:hidden}}
.ch{{padding:16px 20px;background:#263548;border-bottom:1px solid #334155;font-size:14px;font-weight:600;color:#e2e8f0}}
table{{width:100%;border-collapse:collapse}}
th{{padding:10px 12px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;background:#162032;border-bottom:1px solid #334155}}
tr:hover{{background:rgba(255,255,255,.02)}}
.pb{{background:#374151;border-radius:4px;height:10px;width:100%;margin:8px 0}}
.pf{{border-radius:4px;height:10px}}
.footer{{padding:24px 48px;text-align:center;color:#475569;font-size:12px;border-top:1px solid #1e293b;margin-top:16px}}
</style></head><body>
<div class="hdr">
  <div class="hdr-top"><div class="logo">SIRP Platform — Incident Management QA</div><div class="rid">RUN: {run_id}</div></div>
  <h1>Incident Management — End-to-End Test Report</h1>
  <div class="sub">Create Ticket → All Tabs → OmniSense Agents → Artifacts → Comments</div>
  <div class="meta">
    <div class="mi">Date: <span>{datetime.now().strftime("%B %d, %Y")}</span></div>
    <div class="mi">Time: <span>{datetime.now().strftime("%H:%M:%S")}</span></div>
    <div class="mi">Environment: <span>demo3.sirp.io</span></div>
    <div class="mi">Prepared by: <span>Saifa — QA Engineer</span></div>
    <div class="mi">Framework: <span>Playwright + pytest</span></div>
  </div>
</div>
<div class="content">
  <div class="metrics">
    <div class="metric"><div class="mv" style="color:#e2e8f0">{total}</div><div class="ml">Total Tests</div></div>
    <div class="metric"><div class="mv" style="color:#22c55e">{len(passed)}</div><div class="ml">Passed</div></div>
    <div class="metric"><div class="mv" style="color:#ef4444">{len(failed)}</div><div class="ml">Failed</div></div>
    <div class="metric"><div class="mv" style="color:{bar}">{pct}%</div><div class="ml">Pass Rate</div></div>
  </div>
  <div class="card" style="padding:20px 24px;margin-bottom:24px">
    <div style="display:flex;justify-content:space-between;margin-bottom:6px">
      <span style="font-size:13px;color:#94a3b8">Overall pass rate</span>
      <span style="font-size:13px;font-weight:600;color:{bar}">{pct}%</span>
    </div>
    <div class="pb"><div class="pf" style="width:{pct}%;background:{bar}"></div></div>
  </div>
  <div class="card">
    <div class="ch">Step-by-Step Test Results</div>
    <table>
      <thead><tr><th>#</th><th>Time</th><th>Test Step</th><th>Status</th><th>Detail / Evidence</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>
<div class="footer">SIRP IM E2E Report • {datetime.now().strftime("%Y-%m-%d %H:%M")} • Confidential — Internal QA Use Only</div>
</body></html>"""

    p = report_dir / f"im_e2e_report_{run_id}.html"
    p.write_text(html, encoding="utf-8")
    print(f"\n{'='*60}\n  REPORT: {p.resolve()}\n{'='*60}\n")
