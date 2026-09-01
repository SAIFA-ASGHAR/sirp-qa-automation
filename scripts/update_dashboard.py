"""
scripts/update_dashboard.py
----------------------------
Parses pytest output and updates docs/data.json for the live dashboard.
Runs automatically in GitHub Actions after tests complete.
"""

import json
import re
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# PKT = UTC+5 (Pakistan Standard Time)
PKT = timezone(timedelta(hours=5))

DOCS_DATA = Path("docs/data.json")
REPORTS_DIR = Path("reports")


def parse_pytest_output(filepath, suite_name):
    path = Path(filepath)
    if not path.exists():
        print(f"  Skipping {suite_name}: no output file at {filepath}")
        return None

    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"  Skipping {suite_name}: empty output")
        return None

    results = []
    now = datetime.now(PKT)

    # Collect screenshot filenames from output
    screenshots = {}  # test_name -> filename
    for line in text.splitlines():
        ss_match = re.search(r'Screenshot:\s+reports/screenshots/(.+\.png)', line)
        if ss_match:
            ss_file = ss_match.group(1)
            # Extract test name from filename pattern: STATUS_testname_HHMMSS.png
            parts = ss_file.split("_", 1)
            if len(parts) > 1:
                test_key = parts[1].rsplit("_", 1)[0]  # remove timestamp
                screenshots[test_key] = ss_file

    # Parse our custom log output: [PASS] TC01 — Navigate to IM
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.search(r'\[(PASS|FAIL)\]\s+(.+)', line)
        if match:
            status = match.group(1)
            step = match.group(2).strip()
            # Check if next line has detail (indented)
            detail = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.startswith("       "):
                    detail = next_line.strip()

            # Try to find matching screenshot
            screenshot = ""
            step_clean = step.lower().replace(" ", "_").replace("—", "").replace("-", "_")
            for key, fname in screenshots.items():
                if key in step_clean or step_clean in key:
                    screenshot = fname
                    break

            results.append({
                "step": step,
                "status": status,
                "detail": detail,
                "time": now.strftime("%H:%M:%S"),
                "screenshot": screenshot,
            })

    # Fallback: parse pytest PASSED/FAILED lines
    if not results:
        for line in lines:
            m = re.search(r'(PASSED|FAILED)\s+tests/\S+::(?:\S+::)?(\S+)', line)
            if m:
                status = "PASS" if m.group(1) == "PASSED" else "FAIL"
                name = m.group(2).replace("test_", "TC").replace("_", " ").title()
                results.append({"step": name, "status": status, "detail": "", "time": now.strftime("%H:%M:%S")})

    # Last fallback: just count from summary line
    if not results:
        p = re.search(r'(\d+) passed', text)
        f = re.search(r'(\d+) failed', text)
        if p:
            for i in range(int(p.group(1))):
                results.append({"step": f"Test {i+1}", "status": "PASS", "detail": "", "time": now.strftime("%H:%M:%S")})
        if f:
            for i in range(int(f.group(1))):
                results.append({"step": f"Failed test {i+1}", "status": "FAIL", "detail": "", "time": now.strftime("%H:%M:%S")})

    if not results:
        print(f"  No parseable results from {filepath}")
        return None

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)

    # Extract duration from pytest summary
    duration = 0
    dur_match = re.search(r'in\s+([\d.]+)s', text)
    if dur_match:
        duration = float(dur_match.group(1))

    run = {
        "suite": suite_name,
        "run_id": now.strftime("%Y%m%d_%H%M%S"),
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "duration_s": duration,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / total) * 100, 1) if total else 0,
        "environment": "demo3.sirp.io",
        "results": results,
    }

    print(f"  {suite_name}: {passed}/{total} passed ({run['pass_rate']}%)")
    return run


def main():
    print("\n=== Updating QA Dashboard ===\n")

    # Load existing data
    data = {"runs": [], "suites": {}}
    if DOCS_DATA.exists():
        try:
            data = json.loads(DOCS_DATA.read_text())
        except Exception:
            pass

    new_runs = []

    # Parse each suite output
    im = parse_pytest_output(REPORTS_DIR / "im_output.txt", "incident_management")
    if im:
        new_runs.append(im)

    auto = parse_pytest_output(REPORTS_DIR / "autonomy_output.txt", "autonomy_automation")
    if auto:
        new_runs.append(auto)

    # Update
    for run in new_runs:
        data["runs"].append(run)
        data["suites"][run["suite"]] = {
            "last_run": run["timestamp"],
            "last_passed": run["passed"],
            "last_failed": run["failed"],
            "last_total": run["total"],
            "last_rate": run["pass_rate"],
        }

    data["runs"] = data["runs"][-50:]

    DOCS_DATA.parent.mkdir(exist_ok=True)
    DOCS_DATA.write_text(json.dumps(data, indent=2))
    print(f"\n  Dashboard data written to {DOCS_DATA}")
    print("\n=== Done ===\n")


if __name__ == "__main__":
    main()
