# SIRP QA Automation Suite

**End-to-end test automation framework for a security incident response (SOAR) platform**, covering Incident Management, Autonomy, Entities, and Threat Intelligence modules — plus an independent AI-judge layer for evaluating an in-product AI assistant.

🔗 **Live Dashboard:** https://saifa-asghar.github.io/sirp-qa-automation/
📦 **Repo:** https://github.com/SAIFA-ASGHAR/sirp-qa-automation

---

## Overview

This project automates end-to-end QA for **SIRP** (OmniSense), a security incident response platform. It exercises real user workflows — creating tickets, running AI-driven analyst agents, managing entities and threat intel, and validating an in-app AI assistant's answers — across a live demo environment.

Built solo as a QA engineer to move a platform's regression testing from fully manual to automated, with a public dashboard for stakeholder visibility.

## Why this project stands out

- **Not tutorial-following** — this automates a real, complex, actively-changing product (React/Ant Design), with all the flaky-selector, race-condition, and dynamic-ID problems that come with it. See [Engineering Challenges](#engineering-challenges--solutions) below.
- **AI-evaluating-AI** — a separate suite uses the Claude API as an independent judge to score responses from the platform's built-in AI assistant against expected concepts, MITRE ATT&CK references, and hallucination checks.
- **CI/CD integrated** — GitHub Actions runs suites on demand or on relevant code changes, and a bot commits results back to a live dashboard.
- **Evidence-first** — every test step captures a screenshot; pass/fail is corroborated visually, not just asserted.

## Tech Stack

| Layer | Tools |
|---|---|
| Test framework | Python 3, pytest |
| Browser automation | Playwright (sync API) |
| Target UI | React + Ant Design |
| AI evaluation | Anthropic Claude API (independent judge) |
| CI/CD | GitHub Actions (manual dispatch + auto-trigger) |
| Reporting | Custom dark-themed HTML dashboard, GitHub Pages |

## Test Coverage

| Suite | Status | Notes |
|---|---|---|
| **Incident Management** | 18/18 passing | Full lifecycle: create ticket → detail tabs → OmniSense AI agents → artifacts → comments → tasks → entities → remediation → OmniMap → logs → context panel |
| **Autonomy** | 26 tests | Applications, Artifact Types, Actions, Ingestion Sources |
| **Entities** | 10 tests | Navigate, create, grid verify, edit status, detail view, relationships, related tabs, OmniMap, overview |
| **Threat Intelligence** | 12 tests | Actively stabilizing |
| **SARA AI Assistant** | Separate suite | 37-question bank, randomized per run, judged by Claude API against expected concepts + MITRE ATT&CK references + hallucination detection |

## Architecture

```
sirp-qa-automation/
├── tests/
│   ├── test_incident_management_e2e.py
│   ├── test_autonomy_automation_e2e.py
│   ├── test_entities_e2e.py
│   ├── test_threat_intelligence_e2e.py
│   └── test_sara_advanced.py          # AI-judge evaluation suite
├── utils/
│   ├── login.py                       # shared auth helper
│   └── sara_question_bank.py          # randomized question bank
├── scripts/
│   └── update_dashboard.py            # parses pytest output → docs/data.json
├── docs/
│   ├── index.html                     # live dashboard (GitHub Pages)
│   └── data.json                      # dashboard data source
└── .github/workflows/run-tests.yml    # CI/CD pipeline
```

**Fixture pattern:** each suite uses a module-scoped Playwright fixture built on a shared `browser` fixture, logging in once per suite. A `log()` helper records step-by-step results, which feed a custom HTML report generated in `pytest_sessionfinish`.

**Dashboard data flow:** test runs write structured `[PASS]`/`[FAIL]` + `Screenshot:` lines to stdout → `scripts/update_dashboard.py` parses this into `docs/data.json` → the dashboard reads the JSON directly (avoiding GitHub API rate limits) and polls the Actions API for live run status.

## Engineering Challenges & Solutions

Automating a modern React/Ant Design app surfaces problems that don't show up in framework tutorials:

- **Unstable auto-generated IDs** (`#rc_select_33` changes between renders) → built a `select_by_label()` helper that resolves an Ant Design `.ant-select` via its visible label text through XPath, instead of relying on IDs.
- **Ghost dropdown popups** — Ant Design keeps hidden dropdown clones in the DOM → all dropdown interactions scope to `.ant-select-dropdown:not(.ant-select-dropdown-hidden)`.
- **White-screen crashes from naive automation** — iterating over *all* DOM elements to dismiss banners during React re-renders reliably crashed the app; fixed by targeting one specific element instead of iterating. Similarly, pressing `Escape` to close dropdowns could trigger unintended SPA route changes — replaced with a body-click dismissal instead.
- **Rich-text editor targeting** — multiple Quill (`.ql-editor`) instances exist on one page (comments, AI panel); targets the correct one via its `data-placeholder` attribute rather than a generic selector.
- **Long-running async AI agents** — a stability-based polling strategy (spinner absence + no "processing/analyzing" keywords + 3 consecutive unchanged DOM snapshots = considered stable) handles multi-agent workflows that can run up to 10 minutes, instead of a single fixed timeout.
- **Grid ID ≠ detail-view ID** — the platform's grid row ID doesn't match its internal detail-page ID, so direct URL navigation is unreliable; tests always navigate via the UI's own Actions → View action.

## AI-Judge Evaluation Layer

A second, independent suite (`test_sara_advanced.py`) tests the platform's built-in AI assistant by:
1. Randomly sampling questions each run from a 37-question bank (weighted for category coverage), so test data doesn't go stale.
2. Sending each question through the real UI and capturing the assistant's live response.
3. Passing the response to the Claude API, prompted as a strict evaluator, to score it against expected concepts, forbidden ("must not say") terms, and MITRE ATT&CK references — with a keyword-matching fallback if no API key is configured.
4. Generating a manager-readable HTML report with hallucination flags and category-level pass rates.

## CI/CD

- GitHub Actions workflow with manual dispatch (choose suite: `im` / `autonomy` / `entities` / `all`) and auto-trigger on changes to `tests/`, `utils/`, or `conftest.py`.
- Runs headless (`HEADLESS=1`), credentials injected via repository secrets.
- Bot commits updated dashboard data and screenshots back to the repo, which required a specific git workflow (`stash` → `rebase` → `pop`) to handle frequent divergence with CI-generated commits.

## Running Locally

```bash
git clone https://github.com/SAIFA-ASGHAR/sirp-qa-automation.git
cd sirp-qa-automation
pip install -r requirements.txt
playwright install

# copy .env.example to .env and fill in your own credentials
cp .env.example .env

pytest tests/test_incident_management_e2e.py -v -s
pytest tests/test_incident_management_e2e.py -v -s --html=reports/im_report.html
```

> **Note:** credentials are read from environment variables (`SIRP_EMAIL`, `SIRP_PASSWORD`) — never commit real credentials to `login.py` or anywhere else in the repo.

---

*Built and maintained by Saifa — QA Engineer.*
