# WorkspaceLab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local experiment console that runs 10 Workspace personas / 6 agents through 3 manufacturing scenarios against Mock or real Google Workspace.

**Architecture:** Python `http.server` + SQLite backend with a scenario-driven simulator and a swappable `WorkspaceAdapter` (Mock / Google). Vanilla JS dashboard polls JSON endpoints for live actions, personas, metrics, events and report.

**Tech Stack:** Python 3.13, sqlite3, http.server, google-api-python-client + google-auth (real adapter), vanilla HTML/CSS/JS.

**Spec:** `docs/design.md`

## Global Constraints

- Real mode defaults to `DRY_RUN=1`; no external email without allowlist and explicit UI switch.
- Never send to non-allowlisted recipients.
- Mock mode must work with no Google credentials.
- One experiment at a time; max 200 actions; kill switch stops the loop.
- All actions logged with actor, tool, target, status, timestamp.
- No MCP/Cloudflare dependency for the local tool.

## Review Focus

- Real mode with missing credentials must fail closed, not silently send.
- Non-allowlisted recipient must be rejected before API call.
- Pause must stop new actions; report must still be readable.
- Reset must not delete exported reports.
- Dashboard must show errors, not just happy-path actions.

---

### Task 1: Scaffold, config, SQLite store

**Files:** `engine/store.py`, `engine/models.py`, `tests/test_store.py`, `.env.example`, `requirements.txt`

- [ ] Create store with tables `experiments`, `actions`, `metrics`, `events`.
- [ ] Add insert/list methods and a reset.
- [ ] Test insert/list/reset.

### Task 2: Personas, scenarios, simulator

**Files:** `engine/personas.py`, `engine/scenarios.py`, `engine/simulator.py`, `tests/test_simulator.py`

- [ ] 10 personas, 6 agents.
- [ ] 3 scenarios with ordered steps and metrics.
- [ ] Simulator start/pause/reset/inject with background thread.
- [ ] Mock run produces actions and metrics.

### Task 3: Workspace adapters

**Files:** `engine/workspace.py`, `tests/test_workspace.py`

- [ ] Adapter interface and `ActionResult`.
- [ ] Mock adapter.
- [ ] Google adapter with lazy imports, dry-run, allowlist, Gmail/Drive/Docs/Sheets/Calendar/Forms.
- [ ] Fail closed without credentials.

### Task 4: HTTP API + static server

**Files:** `app.py`, `tests/test_api.py`

- [ ] `GET /api/state`, `/api/personas`, `/api/actions`, `/api/metrics`, `/api/report`
- [ ] `POST /api/start`, `/api/pause`, `/api/reset`, `/api/event`, `/api/mode`
- [ ] Serve `web/` static files; JSON errors.

### Task 5: Dashboard

**Files:** `web/index.html`, `web/styles.css`, `web/app.js`

- [ ] Control room layout: status, mode, run/pause/reset, kill.
- [ ] Persona roster, live action feed, metrics, event injection.
- [ ] Report preview + download.

### Task 6: Report, docs, E2E verification

**Files:** `engine/report.py`, `README.md`, `tests/test_e2e.py`

- [ ] Markdown/HTML report with timeline, metrics, failures, recommendation.
- [ ] README with mock run + real setup + safety.
- [ ] Run mock E2E; screenshot dashboard; verify report.
