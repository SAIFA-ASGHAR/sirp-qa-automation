"""
test_sara_advanced.py
---------------------
Advanced SARA AI Test Suite with:
  - Random question selection (new set every run)
  - Claude AI as judge (evaluates SARA responses)
  - MITRE ATT&CK cross-reference
  - Professional HTML report for manager presentation

Run:
    pytest tests/test_sara_advanced.py -v -s
    pytest tests/test_sara_advanced.py -v -s --html=sara_report.html
"""

import os, time, random, json, re, requests, pytest
from datetime import datetime
from pathlib import Path
from playwright.sync_api import Page, expect
from utils.login import login
from utils.sara_question_bank import QUESTION_BANK, CATEGORIES

# ── Config ─────────────────────────────────────────────────────────────────
SARA_URL       = "https://demo3.sirp.io/sara-ai-assistant"
ANTHROPIC_URL  = "https://api.anthropic.com/v1/messages"
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
SARA_TIMEOUT   = 90000   # 90 seconds for SARA to respond
QUESTIONS_PER_RUN = 10   # how many questions per test run (random selection)
REPORT_DIR     = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

# ── Results store (shared across all tests in a run) ───────────────────────
RUN_RESULTS = []
RUN_ID      = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── Judge system prompt ────────────────────────────────────────────────────
JUDGE_PROMPT = """You are a strict cybersecurity QA evaluator assessing SARA,
an AI security assistant built on SIRP SOAR platform powered by OmniSense.

You will receive:
- The question asked
- Expected keywords/concepts
- Things SARA must NOT say (hallucination check)
- SARA's actual response

Evaluate strictly. Return ONLY valid JSON:
{
  "verdict": "PASS" or "FAIL",
  "score": 0-10,
  "reason": "one clear sentence",
  "hallucination_detected": true or false,
  "missing_concepts": ["concept1", "concept2"],
  "strengths": "what SARA did well"
}

Rules:
- FAIL if response is empty, too vague, or missing more than half expected concepts
- FAIL if must_not words appear in response (hallucination)
- PASS if at least 50% of expected keywords are addressed
- For limitation tests: PASS if SARA gracefully declines rather than fabricating
"""


# ── Random question selection (new every run!) ─────────────────────────────
def select_questions_for_run(n: int = QUESTIONS_PER_RUN) -> list:
    """
    Picks a fresh random set of questions every run.
    Ensures good category coverage — at least one from each major category.
    """
    selected = []
    # First: pick one HIGH severity from each category
    for cat in CATEGORIES:
        cat_qs = [q for q in QUESTION_BANK if q["category"] == cat and q["severity"] == "high"]
        if cat_qs:
            selected.append(random.choice(cat_qs))

    # Fill remaining slots randomly from full bank
    remaining = [q for q in QUESTION_BANK if q not in selected]
    random.shuffle(remaining)
    selected += remaining[:max(0, n - len(selected))]

    # Final shuffle so order is also random
    random.shuffle(selected)
    return selected[:n]


# ── Claude judge ───────────────────────────────────────────────────────────
def evaluate_response(question: str, expected: list, must_not: list,
                       mitre_ref: str, sara_response: str) -> dict:
    if not sara_response or len(sara_response.strip()) < 5:
        return {
            "verdict": "FAIL",
            "score": 0,
            "reason": "SARA returned empty or too short response",
            "hallucination_detected": False,
            "missing_concepts": expected,
            "strengths": "N/A"
        }

    # Hallucination check
    for bad_word in must_not:
        if bad_word.lower() in sara_response.lower():
            return {
                "verdict": "FAIL",
                "score": 1,
                "reason": f"Hallucination detected — SARA mentioned forbidden term: '{bad_word}'",
                "hallucination_detected": True,
                "missing_concepts": [],
                "strengths": "N/A"
            }

    # No API key — keyword fallback
    if not ANTHROPIC_KEY:
        if not expected:
            return {"verdict": "PASS", "score": 8, "reason": "No keywords required — response received",
                    "hallucination_detected": False, "missing_concepts": [], "strengths": "Response received"}
        rl = sara_response.lower()
        matched   = [k for k in expected if k.lower() in rl]
        missing   = [k for k in expected if k.lower() not in rl]
        score     = int((len(matched) / len(expected)) * 10)
        verdict   = "PASS" if score >= 5 else "FAIL"
        return {"verdict": verdict, "score": score,
                "reason": f"Keyword match {len(matched)}/{len(expected)}: {matched}",
                "hallucination_detected": False,
                "missing_concepts": missing,
                "strengths": f"Matched: {matched}"}

    # Claude as judge
    mitre_note = f"\nMITRE reference: {mitre_ref}" if mitre_ref else ""
    prompt = f"""Question: {question}{mitre_note}
Expected concepts: {expected}
Must NOT appear: {must_not}
SARA response:
{sara_response}
Evaluate."""

    try:
        resp = requests.post(
            ANTHROPIC_URL,
            headers={"Content-Type": "application/json",
                     "x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 300,
                  "system": JUDGE_PROMPT,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        text = re.sub(r"```json\n?|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        return {"verdict": "ERROR", "score": 0,
                "reason": f"Judge error: {e}",
                "hallucination_detected": False,
                "missing_concepts": expected,
                "strengths": "N/A"}


# ── Start a fresh SARA chat (click New Chat button) ────────────────────────
def start_new_chat(page: Page):
    """Click 'New Chat' to reset conversation between questions."""
    try:
        new_chat_btn = page.locator("button:has-text('New Chat'), a:has-text('New Chat')").first
        if new_chat_btn.is_visible():
            new_chat_btn.click()
            time.sleep(2)
    except Exception:
        pass  # if not found just continue


# ── Send message to SARA and capture response ──────────────────────────────
def send_to_sara(page: Page, message: str) -> str:
    """
    Types a message into SARA's real input box, submits it,
    waits for the 'thinking' indicator to finish, captures response.

    Real UI (from screenshot):
    - Input: textarea with placeholder 'Describe what you need help with...'
    - Send: arrow button to the right of input
    - Thinking indicator: 'Ran N thinking step' text appears while processing
    """
    # Start fresh chat for each question
    start_new_chat(page)
    time.sleep(1)

    # Find SARA's real input box
    chat_input = page.locator(
        "textarea[placeholder*='Describe what you need']"
    ).first
    expect(chat_input).to_be_visible(timeout=20000)
    chat_input.click()
    chat_input.fill(message)

    # Click the send arrow button (right side of input)
    try:
        send_btn = page.locator("button[aria-label*='send'], button[aria-label*='Send'], .send-button").first
        if send_btn.is_visible():
            send_btn.click()
        else:
            chat_input.press("Enter")
    except Exception:
        chat_input.press("Enter")

    time.sleep(2)

    # Wait for "thinking" indicator to appear then disappear
    # SARA shows "Ran N thinking step" while processing
    try:
        page.wait_for_selector(
            "text=thinking step, text=Ran 1, .thinking, .loading",
            timeout=10000
        )
    except Exception:
        pass  # might not appear immediately

    # Now wait for it to finish (disappear or stabilize)
    try:
        page.wait_for_function(
            """() => {
                const thinking = document.body.innerText.includes('thinking step');
                const spinner  = document.querySelector('.ant-spin-spinning, .loading');
                return !thinking && !spinner;
            }""",
            timeout=SARA_TIMEOUT
        )
    except Exception:
        pass

    # Extra buffer for full render
    time.sleep(3)

    # ── Capture SARA's response ────────────────────────────────────────────
    # From screenshot: response appears as a text bubble in center of page
    # Try multiple selectors in order of reliability
    response_selectors = [
        # Most specific — SARA response bubbles
        ".sara-message", ".assistant-message", "[data-role='assistant']",
        # Ant Design comment content
        ".ant-comment-content-detail p",
        # Generic message bubbles
        ".message:not(.user-message)", ".chat-message:not(.user)",
        # Fallback — any paragraph in main content
        "main p",
    ]

    for sel in response_selectors:
        try:
            els = page.locator(sel).all()
            if els:
                # Get last element (most recent response)
                text = els[-1].inner_text().strip()
                if len(text) > 10:
                    return text[:2000]
        except Exception:
            continue

    # Last resort — grab full page text and extract after our message
    try:
        body_text = page.locator("body").inner_text()
        parts = body_text.split(message)
        if len(parts) > 1:
            # Take text after our message, skip "Ran N thinking step" line
            after = parts[-1].strip()
            lines = [l for l in after.splitlines() if l.strip()
                     and "thinking step" not in l
                     and "Describe what" not in l]
            return "\n".join(lines[:30]).strip()[:2000]
    except Exception:
        pass

    return ""


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def selected_questions():
    """Pick a fresh random set of questions once per session."""
    qs = select_questions_for_run(QUESTIONS_PER_RUN)
    print(f"\n  Selected {len(qs)} questions for this run (RUN_ID: {RUN_ID})")
    for q in qs:
        print(f"    [{q['id']}] {q['category']} — {q['question'][:60]}")
    return qs


@pytest.fixture(scope="module")
def sara_page(browser):
    """Shared browser session — logs in once, stays on SARA page."""
    context = browser.new_context()
    page = context.new_page()
    login(page)
    page.goto(SARA_URL, wait_until="networkidle", timeout=30000)
    time.sleep(3)
    yield page
    context.close()


# ── Main Test ────────────────────────────────────────────────────────────────
class TestSARAAdvanced:

    def test_sara_page_accessible(self, sara_page):
        """Verify SARA page loads and chat input is ready."""
        expect(sara_page).to_have_url("**/sara-ai-assistant**")
        chat_input = sara_page.locator(
            "textarea[placeholder*='Describe what you need']"
        ).first
        expect(chat_input).to_be_visible(timeout=20000)
        print("\n  SARA page loaded and chat input is ready!")

    @pytest.mark.parametrize("question_data",
                             select_questions_for_run(QUESTIONS_PER_RUN),
                             ids=[q["id"] for q in select_questions_for_run(QUESTIONS_PER_RUN)])
    def test_sara_response(self, sara_page, question_data):
        """Send question to SARA, evaluate response, record result."""
        q         = question_data
        test_id   = q["id"]
        question  = q["question"]
        expected  = q["expected"]
        must_not  = q["must_not"]
        mitre_ref = q["mitre_ref"]
        category  = q["category"]

        print(f"\n{'─'*65}")
        print(f"  [{test_id}] {category}")
        print(f"  Q: {question}")

        start_time = time.time()
        response   = send_to_sara(sara_page, question)
        duration   = round(time.time() - start_time, 1)

        print(f"  Response ({len(response)} chars, {duration}s): {response[:150]}...")

        # Evaluate
        result = evaluate_response(question, expected, must_not, mitre_ref, response)

        print(f"  Verdict: {result['verdict']}  Score: {result.get('score','?')}/10")
        print(f"  Reason: {result.get('reason','')}")

        # Store for report
        RUN_RESULTS.append({
            "id":          test_id,
            "category":    category,
            "question":    question,
            "response":    response,
            "verdict":     result["verdict"],
            "score":       result.get("score", 0),
            "reason":      result.get("reason", ""),
            "hallucination": result.get("hallucination_detected", False),
            "missing":     result.get("missing_concepts", []),
            "strengths":   result.get("strengths", ""),
            "mitre_ref":   mitre_ref,
            "duration":    duration,
            "severity":    q["severity"],
            "timestamp":   datetime.now().strftime("%H:%M:%S"),
        })

        # Assert
        assert result["verdict"] == "PASS", (
            f"[{test_id}] FAILED — {result.get('reason','')}\n"
            f"Response: {response[:300]}"
        )


# ── Report generation (runs after all tests) ────────────────────────────────
def pytest_sessionfinish(session, exitstatus):
    """Auto-generate HTML report after test session ends."""
    if not RUN_RESULTS:
        return
    _generate_html_report(RUN_RESULTS)


def _generate_html_report(results: list):
    passed   = [r for r in results if r["verdict"] == "PASS"]
    failed   = [r for r in results if r["verdict"] == "FAIL"]
    errors   = [r for r in results if r["verdict"] == "ERROR"]
    total    = len(results)
    pass_pct = round((len(passed) / total) * 100) if total else 0
    avg_score = round(sum(r["score"] for r in results) / total, 1) if total else 0
    hallucinations = sum(1 for r in results if r["hallucination"])

    # Category breakdown
    cat_stats = {}
    for r in results:
        c = r["category"]
        cat_stats.setdefault(c, {"pass": 0, "fail": 0, "total": 0})
        cat_stats[c]["total"] += 1
        if r["verdict"] == "PASS":
            cat_stats[c]["pass"] += 1
        else:
            cat_stats[c]["fail"] += 1

    report_path = REPORT_DIR / f"sara_report_{RUN_ID}.html"

    def badge(verdict):
        if verdict == "PASS":
            return '<span style="background:#166534;color:#dcfce7;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">PASS</span>'
        elif verdict == "FAIL":
            return '<span style="background:#991b1b;color:#fee2e2;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">FAIL</span>'
        return '<span style="background:#92400e;color:#fef3c7;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">ERROR</span>'

    def sev_badge(sev):
        colors = {"high": ("#991b1b", "#fee2e2"), "medium": ("#92400e", "#fef3c7"), "low": ("#166534", "#dcfce7")}
        bg, fg = colors.get(sev, ("#374151", "#f3f4f6"))
        return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:8px;font-size:11px;">{sev.upper()}</span>'

    rows = ""
    for r in results:
        mitre = f'<a href="{r["mitre_ref"]}" target="_blank" style="color:#3b82f6;font-size:11px;">ATT&CK ↗</a>' if r["mitre_ref"] else "—"
        missing = ", ".join(r["missing"]) if r["missing"] else "None"
        halluc = '<span style="color:#ef4444;font-weight:600;">⚠ Yes</span>' if r["hallucination"] else '<span style="color:#22c55e;">No</span>'
        rows += f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:10px 8px;color:#9ca3af;font-size:12px;">{r['id']}</td>
          <td style="padding:10px 8px;">
            <div style="font-size:12px;color:#6b7280;margin-bottom:4px;">{r['category']} {sev_badge(r['severity'])}</div>
            <div style="font-size:13px;color:#e5e7eb;font-weight:500;">{r['question']}</div>
          </td>
          <td style="padding:10px 8px;max-width:320px;">
            <div style="font-size:12px;color:#d1d5db;line-height:1.5;max-height:80px;overflow:hidden;">{r['response'][:300]}{'...' if len(r['response'])>300 else ''}</div>
          </td>
          <td style="padding:10px 8px;text-align:center;">{badge(r['verdict'])}</td>
          <td style="padding:10px 8px;text-align:center;color:#f59e0b;font-weight:600;">{r['score']}/10</td>
          <td style="padding:10px 8px;font-size:11px;color:#9ca3af;">{r['reason'][:80]}</td>
          <td style="padding:10px 8px;text-align:center;">{halluc}</td>
          <td style="padding:10px 8px;text-align:center;">{mitre}</td>
          <td style="padding:10px 8px;text-align:center;color:#6b7280;font-size:11px;">{r['duration']}s</td>
        </tr>"""

    cat_rows = ""
    for cat, stats in cat_stats.items():
        pct = round((stats["pass"] / stats["total"]) * 100)
        bar_color = "#22c55e" if pct >= 70 else "#f59e0b" if pct >= 50 else "#ef4444"
        cat_rows += f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:10px 12px;color:#e5e7eb;font-weight:500;">{cat}</td>
          <td style="padding:10px 12px;text-align:center;color:#e5e7eb;">{stats['total']}</td>
          <td style="padding:10px 12px;text-align:center;color:#22c55e;">{stats['pass']}</td>
          <td style="padding:10px 12px;text-align:center;color:#ef4444;">{stats['fail']}</td>
          <td style="padding:10px 12px;">
            <div style="background:#374151;border-radius:4px;height:8px;width:100%;">
              <div style="background:{bar_color};border-radius:4px;height:8px;width:{pct}%;"></div>
            </div>
            <div style="font-size:11px;color:#9ca3af;margin-top:2px;">{pct}%</div>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SARA AI QA Report — {RUN_ID}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e5e7eb; }}
  .header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #1e40af 100%); padding: 40px 48px; }}
  .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }}
  .logo {{ font-size: 13px; color: #a5b4fc; letter-spacing: 2px; text-transform: uppercase; font-weight: 600; }}
  .run-id {{ font-size: 11px; color: #818cf8; background: rgba(99,102,241,0.2); padding: 4px 10px; border-radius: 8px; }}
  h1 {{ font-size: 28px; font-weight: 700; color: #fff; margin: 12px 0 4px; }}
  .subtitle {{ color: #a5b4fc; font-size: 14px; }}
  .meta {{ display: flex; gap: 24px; margin-top: 16px; }}
  .meta-item {{ font-size: 12px; color: #818cf8; }}
  .meta-item span {{ color: #c7d2fe; font-weight: 500; }}
  .content {{ padding: 32px 48px; max-width: 1400px; margin: 0 auto; }}
  .metrics {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 32px; }}
  .metric {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center; }}
  .metric-value {{ font-size: 32px; font-weight: 700; margin-bottom: 4px; }}
  .metric-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }}
  .section {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; margin-bottom: 24px; overflow: hidden; }}
  .section-header {{ padding: 16px 20px; background: #263548; border-bottom: 1px solid #334155; display: flex; align-items: center; gap: 10px; }}
  .section-title {{ font-size: 14px; font-weight: 600; color: #e2e8f0; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ padding: 10px 8px; text-align: left; font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; background: #162032; border-bottom: 1px solid #334155; }}
  tr:hover {{ background: rgba(255,255,255,0.02); }}
  .footer {{ padding: 24px 48px; text-align: center; color: #475569; font-size: 12px; border-top: 1px solid #1e293b; margin-top: 16px; }}
  .pass-color {{ color: #22c55e; }}
  .fail-color {{ color: #ef4444; }}
  .warn-color {{ color: #f59e0b; }}
  .disclaimer {{ background: #1e293b; border: 1px solid #334155; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; font-size: 13px; color: #94a3b8; line-height: 1.6; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-top">
    <div class="logo">SIRP Platform — OmniSense AI</div>
    <div class="run-id">RUN ID: {RUN_ID}</div>
  </div>
  <h1>SARA AI Assistant — QA Evaluation Report</h1>
  <div class="subtitle">Automated test evaluation using Playwright + Claude AI Judge</div>
  <div class="meta">
    <div class="meta-item">Date: <span>{datetime.now().strftime("%B %d, %Y")}</span></div>
    <div class="meta-item">Time: <span>{datetime.now().strftime("%H:%M:%S")}</span></div>
    <div class="meta-item">Environment: <span>demo3.sirp.io</span></div>
    <div class="meta-item">Prepared by: <span>Saifa — QA Engineer</span></div>
    <div class="meta-item">Framework: <span>Playwright + pytest + Claude AI</span></div>
  </div>
</div>

<div class="content">

  <div class="disclaimer">
    <strong style="color:#93c5fd;">About this report:</strong> This report was auto-generated by an 
    automated QA framework that sends test questions to SARA, captures its responses, and uses 
    Claude AI as an independent judge to evaluate accuracy against MITRE ATT&CK knowledge and 
    the SARA POC scope. Questions are randomly selected each run to ensure broad coverage.
  </div>

  <div class="metrics">
    <div class="metric">
      <div class="metric-value" style="color:#e2e8f0;">{total}</div>
      <div class="metric-label">Total Tests</div>
    </div>
    <div class="metric">
      <div class="metric-value pass-color">{len(passed)}</div>
      <div class="metric-label">Passed</div>
    </div>
    <div class="metric">
      <div class="metric-value fail-color">{len(failed) + len(errors)}</div>
      <div class="metric-label">Failed</div>
    </div>
    <div class="metric">
      <div class="metric-value warn-color">{pass_pct}%</div>
      <div class="metric-label">Pass Rate</div>
    </div>
    <div class="metric">
      <div class="metric-value" style="color:#a78bfa;">{avg_score}/10</div>
      <div class="metric-label">Avg Score</div>
    </div>
  </div>

  {'<div class="metric" style="border-color:#7f1d1d;background:#1c0a0a;padding:12px 20px;border-radius:8px;margin-bottom:24px;font-size:13px;color:#fca5a5;"><strong>⚠ Hallucination Alert:</strong> ' + str(hallucinations) + ' response(s) detected possible hallucination — review highlighted rows below.</div>' if hallucinations else ''}

  <div class="section">
    <div class="section-header">
      <div class="section-title">Category Breakdown</div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Category</th><th>Total</th><th>Passed</th><th>Failed</th><th style="width:200px;">Pass Rate</th>
        </tr>
      </thead>
      <tbody>{cat_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-title">Detailed Test Results</div>
    </div>
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Question</th>
          <th>SARA Response</th>
          <th>Status</th>
          <th>Score</th>
          <th>Evaluation</th>
          <th>Hallucination</th>
          <th>MITRE</th>
          <th>Time</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

</div>

<div class="footer">
  SARA AI QA Report • Auto-generated {datetime.now().strftime("%Y-%m-%d %H:%M")} •
  SIRP Platform — OmniSense AI • Confidential — Internal Use Only
</div>

</body>
</html>"""

    report_path.write_text(html, encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"  REPORT SAVED: {report_path.resolve()}")
    print(f"  Open in Chrome to view the full report!")
    print(f"{'='*60}\n")
