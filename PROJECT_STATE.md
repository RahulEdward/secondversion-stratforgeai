# StratForge AI — Project State & Build Guide

> **Purpose of this file**: A complete handoff document. Any AI model (or human dev) reading this should understand (1) what StratForge AI is, (2) what's already built, (3) what's still pending, (4) how to build each remaining piece, and (5) what the final product looks like — without needing any other context.

**Last updated**: 2026-04-18
**Working directory**: `D:\ai-backtestingapp`
**OS target**: Windows 11 (Mac/Linux deferred to v2)

---

## 1. What is StratForge AI?

A **Windows desktop app** that wraps a Python VectorBT-based algorithmic-trading backtester in a **Claude Code–style chat UI**. The user loads market data (CSV/XLSX), chats with an AI in natural language ("backtest an RSI-oversold + MACD-crossover strategy on this data"), and the AI drives a 10-step validation pipeline that produces a validated strategy + HTML/PDF report.

### The 10-step backtesting flow the app orchestrates
1. Load CSV/XLSX market data
2. Compute technical indicators (15 built-in)
3. AI generates strategy code from user's natural-language prompt
4. VectorBT runs the backtest on historical data
5. Batch optimizer sweeps parameter grids
6. AI evaluates results (returns, Sharpe, drawdown, trade count)
7. Walk-forward + Monte Carlo validation for robustness
8. Strategy gets a composite score
9. HTML report renders in the artifacts pane
10. PDF export via Playwright

### Why it exists (user's motivation)
The user already has a working 10-step VectorBT backtesting framework. They want to expose it through a polished desktop experience so traders can use any AI provider (their own Claude subscription, an API key, or a local Ollama model), load data, prompt in plain English, and get a validated strategy without writing code. Token-efficient + validation-first are explicit goals.

---

## 2. Quick start — run what's built today

```bash
# 1. Install Python deps (one-time)
cd D:\ai-backtestingapp\backend
pip install -r requirements.txt

# 2. Install Node deps (one-time)
cd D:\ai-backtestingapp
npm install

# 3. Dev mode: runs Vite (UI on :5173) + FastAPI (API on :8765) together
npm run dev
```

- UI opens at `http://localhost:5173`
- API health: `http://127.0.0.1:8765/api/health` → `{"status":"ok","version":"0.1.0"}`
- Full API docs (auto): `http://127.0.0.1:8765/docs`

To run only the backend: `cd backend && python main.py`
To run only the UI: `npm run dev:ui`
Type-check: `npm run typecheck`

---

## 3. Locked architectural decisions

These are fixed unless the user explicitly changes them. Do not re-debate.

| Area | Decision |
|------|----------|
| OS | Windows first, Mac/Linux v2 |
| UI framework | Electron + React + TypeScript + Tailwind + shadcn/ui |
| UI look | **Pixel-match of actual Claude Code desktop app** (see §8 for details) |
| Backend | Python 3.11 + FastAPI + VectorBT + Pandas + TA-Lib, localhost HTTP + WebSocket streaming |
| API base URL | `http://127.0.0.1:8765`, all routes under `/api` |
| Data model | Projects → Sessions → Messages (not flat workspaces) |
| Storage | SQLite per-project workspace; OHLCV datasets stored as Parquet; OS keychain for secrets |
| AI providers (4 supported) | (1) Ollama local, (2) API keys (Anthropic / OpenAI / Google), (3) Claude Code subscription via OAuth, (4) API-key fallback |
| Memory summarizer | Always small/cheap model (Haiku / local Llama) — never the user's main model. Reason: keep user's tokens & cost predictable |
| Reports | HTML + PDF via Playwright, shown in artifacts pane |
| Workspaces structure | `AppData/Roaming/StratForge/workspaces/<pj_id>/` with `data/`, `reports/`, `memory/`, `chats.db`, `workspace.json` |
| Name | StratForge AI |
| Offline mode | Automatic when user picks Ollama — no separate toggle |
| License hosting, pricing tiers | **DEFERRED** — decide before Phase 10 |

---

## 4. Tech stack

### Frontend (`/src`, `/electron`)
- **React 18** + **TypeScript 5.6**
- **Vite 5** for dev server + bundling
- **Electron 33** shell (wiring exists but app is currently developed in browser)
- **Tailwind CSS 3.4** with a custom Claude-Code color palette (see [tailwind.config.js](tailwind.config.js))
- **Zustand 5** for state management ([useAppStore.ts](src/store/useAppStore.ts))
- **lucide-react** icons
- **clsx** + **tailwind-merge** via `cn` helper

### Backend (`/backend`)
- **Python 3.11**
- **FastAPI 0.115** + **Uvicorn 0.32**
- **Pandas 2.2** + **NumPy 2.1** — indicator math
- **PyArrow 18** — Parquet I/O
- **python-multipart** — file upload
- **openpyxl** — Excel support
- **[deferred]** vectorbt, TA-Lib, Playwright — added when their phase starts

---

## 5. Build phases — status map

| Phase | Scope | Status |
|-------|-------|--------|
| P1 | App shell + 3-pane UI skeleton | ✅ Done |
| P2 | Workspace (Project + Session) CRUD, backend + UI | ✅ Done |
| P2.5 | UI redesign for pixel-match with Claude Code | ✅ Done (see §8 for verification required) |
| P3 | Data ingestion + Indicator engine | ✅ Backend done + smoke-tested. ⚠️ **UI missing** — no dataset upload/list panel yet |
| P4 | AI providers: Ollama + API keys (Anthropic/OpenAI/Google) | 🔲 Not started |
| P5 | Claude Code OAuth subscription login | 🔲 Not started |
| P6 | AI orchestrator + tool-calling loop | 🔲 Not started |
| P7 | VectorBT backtest + optimize + walk-forward + Monte Carlo | 🔲 Not started |
| P8 | HTML/PDF reports in artifacts pane | 🔲 Not started |
| P9 | Per-workspace auto-memory subsystem | 🔲 Not started |
| P10 | License, auto-update, Windows installer | 🔲 Not started |

---

## 6. What's built today (detailed)

### 6.1 Backend

**Entry point**: [backend/main.py](backend/main.py) — Uvicorn on `127.0.0.1:8765`, reload enabled in dev.
**App factory**: [backend/app/__init__.py](backend/app/__init__.py) — FastAPI + CORS for `localhost:5173`.

**Modules**:
- [backend/app/paths.py](backend/app/paths.py) — resolves `%APPDATA%\StratForge\workspaces` etc.
- [backend/app/schemas.py](backend/app/schemas.py) — Pydantic: Project, Session, Dataset, DatasetPreview, AppState
- [backend/app/storage.py](backend/app/storage.py) — filesystem + SQLite CRUD for projects, sessions, datasets; handles lazy schema migration from the older `chats` table
- [backend/app/data.py](backend/app/data.py) — CSV/TSV/XLSX ingestion with OHLCV alias canonicalization (`ts→time`, `o→open`, `c→close`, etc.), time parsing, numeric coercion, Parquet storage
- [backend/app/indicators.py](backend/app/indicators.py) — 15 indicators, all pure pandas/numpy
- [backend/app/tools.py](backend/app/tools.py) — auto-generates Anthropic-format tool schemas from the indicator registry (15 tools: `compute_sma`, `compute_rsi`, etc.)
- [backend/app/routes.py](backend/app/routes.py) — all HTTP endpoints

**15 indicators shipped** (all with sensible defaults):
- Trend: `sma`, `ema`, `macd`, `ichimoku`, `supertrend`
- Momentum: `rsi`, `stochastic`, `williams_r`, `roc`, `cci`
- Volatility: `bollinger_bands`, `atr`
- Volume: `obv`, `vwap`
- Directional: `adx`

**API endpoints live**:
```
GET    /api/health
GET    /api/tools                                  → 15 tool schemas

GET    /api/projects                               → list
POST   /api/projects                               → {name}
GET    /api/projects/{pid}
PATCH  /api/projects/{pid}                         → rename
DELETE /api/projects/{pid}

GET    /api/projects/{pid}/sessions
POST   /api/projects/{pid}/sessions                → {title}
GET    /api/sessions/{sid}
PATCH  /api/sessions/{sid}                         → rename
DELETE /api/sessions/{sid}

GET    /api/projects/{pid}/datasets
POST   /api/projects/{pid}/datasets                → multipart file upload
GET    /api/datasets/{did}
GET    /api/datasets/{did}/preview?rows=50
DELETE /api/datasets/{did}

POST   /api/datasets/{did}/indicators              → {indicator, params, tail}
GET    /api/app/state                              → active_project_id, active_session_id
PUT    /api/app/state
```

**Smoke test results (2026-04-18)**: Upload 500-row BTC CSV → detected OHLCV, 20-day range, 29 KB parquet. RSI(14) → values 0–100, times aligned. MACD → 3 columns (macd/signal/hist). Bollinger → upper > middle > lower. Unknown indicator → HTTP 400. All green.

### 6.2 Frontend

**Entry**: [src/main.tsx](src/main.tsx) → [src/App.tsx](src/App.tsx) — 3-pane layout: `TitleBar` above, `Sidebar | ChatPane | ArtifactsPane` (artifacts toggleable).

**Shell** (`src/components/shell/`)
- [TitleBar.tsx](src/components/shell/TitleBar.tsx) — Claude Code–style top bar with breadcrumb slot and sidebar toggle

**Sidebar** (`src/components/sidebar/`)
- [SidebarNav.tsx](src/components/sidebar/SidebarNav.tsx), [SidebarTabs.tsx](src/components/sidebar/SidebarTabs.tsx), [SidebarProjects.tsx](src/components/sidebar/SidebarProjects.tsx), [SidebarPinned.tsx](src/components/sidebar/SidebarPinned.tsx), [SidebarUserRow.tsx](src/components/sidebar/SidebarUserRow.tsx), [UserMenuPopup.tsx](src/components/sidebar/UserMenuPopup.tsx) — 5-layer sidebar (icon toolbar, tab pills, flat nav, pinned, project→session tree, user row at bottom)

**Chat center** (`src/components/chat/`)
- [MainHeader.tsx](src/components/chat/MainHeader.tsx) — breadcrumb dropdowns
- [MessageList.tsx](src/components/chat/MessageList.tsx) — static placeholder (no streaming yet)
- [ChatInput.tsx](src/components/chat/ChatInput.tsx) — large pill with "Type / for commands" hint
- [ChatFooter.tsx](src/components/chat/ChatFooter.tsx) — Ask permissions + model picker row
- [ModelPicker.tsx](src/components/chat/ModelPicker.tsx) — popup

**Artifacts** (`src/components/`)
- [ArtifactsPane.tsx](src/components/ArtifactsPane.tsx) — 440px right pane, empty-state only; will host HTML reports in Phase 8

**UI primitives** (`src/components/ui/`)
- [Popup.tsx](src/components/ui/Popup.tsx), [Toast.tsx](src/components/ui/Toast.tsx)

**Dialogs**
- [NewProjectDialog.tsx](src/components/NewProjectDialog.tsx)

**State + API** (`src/store/`, `src/lib/`)
- [useAppStore.ts](src/store/useAppStore.ts) — Zustand: projects, sessionsByProject, active IDs, UI flags (`sidebarTab`, `artifactsOpen`, `theme`, `askPermissions`)
- [api.ts](src/lib/api.ts) — fetch wrapper + typed client for all project/session/app-state endpoints (⚠️ **dataset + indicator endpoints not yet wrapped**)
- [cn.ts](src/lib/cn.ts) — `clsx + twMerge` helper

**Electron** (`electron/`)
- [main.ts](electron/main.ts), [preload.ts](electron/preload.ts) — window boot wired but the app is currently developed via Vite in a browser

---

## 7. What's left to build — phase-by-phase recipes

Each phase below is a standalone build slice. User rule: **lock the plan, then build**. Do not start a phase without confirmation.

### Phase 3.5 — Dataset UI (finishes Phase 3)
**Why first**: backend is ready, but the user has no way to upload data from the app — only via curl/Python. Without this, chat can never be grounded on real data.

**Build steps**:
1. Extend [src/lib/api.ts](src/lib/api.ts) with: `listDatasets(projectId)`, `uploadDataset(projectId, File)`, `getDatasetPreview(id, rows)`, `deleteDataset(id)`, `computeIndicator(datasetId, name, params, tail)`.
2. Add to [src/store/useAppStore.ts](src/store/useAppStore.ts): `datasetsByProject`, `activeDatasetId`, and actions (refresh/upload/delete/setActive).
3. New component `src/components/sidebar/SidebarDatasets.tsx` — list under the active project in the tree, each row shows filename + rows + date-range.
4. New `src/components/DataUploadDropzone.tsx` — drag-drop + file picker, shows progress, calls `uploadDataset`.
5. New `src/components/DatasetPreviewModal.tsx` — table of first 50 rows from `/preview`.
6. [MainHeader.tsx](src/components/chat/MainHeader.tsx): show active dataset chip next to project/session breadcrumb.

**Done when**: user can upload a CSV, see it in the tree, open a preview, and the active dataset is visible in the header.

---

### Phase 4 — AI providers (API keys + Ollama)
**Goal**: make chat actually respond. Support 3 API-key providers + local Ollama.

**Backend build steps**:
1. `pip install anthropic openai google-generativeai httpx`
2. `backend/app/secrets.py` — wrapper around [`keyring`](https://pypi.org/project/keyring/) for OS keychain (Windows Credential Manager).
3. `backend/app/providers/` package: `base.py` (abstract `Provider` interface with `stream_chat(messages, tools) -> AsyncIterator[Chunk]`), `anthropic.py`, `openai.py`, `google.py`, `ollama.py`. Normalize tool-call chunks across SDKs to a single `{type: 'text'|'tool_use', ...}` shape.
4. Add routes: `POST /api/settings/providers/{name}/key` (stores via keyring), `DELETE /api/settings/providers/{name}/key`, `GET /api/settings/providers` (returns which providers have keys + Ollama availability from `GET http://localhost:11434/api/tags`), `GET /api/settings/providers/{name}/models`.
5. Store per-session `provider` + `model` on the session row (add columns via lazy migration in [storage.py](backend/app/storage.py)).

**Frontend build steps**:
1. `src/components/settings/ProvidersSettings.tsx` — toggles, API-key inputs (password-masked), Ollama URL field.
2. Wire the existing [ModelPicker.tsx](src/components/chat/ModelPicker.tsx) to real data: list models from the active provider.
3. Save the picked model onto the session.

**Done when**: user can paste an Anthropic key in settings, pick `claude-opus-4-7` in the model picker, and the picker shows real models.

---

### Phase 5 — Claude Code subscription OAuth
**Goal**: users with a Claude Max/Pro subscription can log in and run the app using their subscription quota instead of an API key.

**Reference**: Anthropic's official Claude Code CLI does this via OAuth device flow. Research the exact endpoints before implementation — this is the most uncertain phase.

**Build steps** (approximate, subject to research):
1. Electron main: register a custom protocol handler (`stratforge://oauth-callback`).
2. Backend: `POST /api/auth/claude/device-start` (initiate device code flow), `POST /api/auth/claude/device-poll`, `GET /api/auth/claude/status`. Tokens stored via keyring.
3. The Anthropic provider (from Phase 4) should accept either an API key **or** an OAuth access token via the `Authorization: Bearer …` header. Refresh tokens on 401.
4. Settings UI: "Sign in with Claude" button that opens the browser for device-code approval.

**Open question for user**: confirm Anthropic exposes this OAuth flow to third-party apps — may need to validate with them before Phase 5 starts.

---

### Phase 6 — AI orchestrator + tool-calling loop
**Goal**: when the user sends a chat message, the backend streams LLM output token-by-token; when the LLM calls a tool (e.g., `compute_rsi`), the backend dispatches to the indicator/backtest executor and feeds the result back into the LLM until a final answer is produced.

**Build steps**:
1. `backend/app/orchestrator.py` — main loop:
   ```
   msgs = load_session_messages()
   while True:
       stream = provider.stream_chat(msgs, tools=all_tools())
       async for chunk in stream:
           yield ws_frame(chunk)           # stream to UI
           if chunk.type == 'tool_use':
               result = await tool_exec.run(chunk.name, chunk.input)
               msgs.append(assistant(chunk)); msgs.append(tool_result(result))
               break
       else:
           break  # natural end of assistant turn
   ```
2. `backend/app/tool_exec.py` — dispatcher that maps tool names (`compute_rsi`, `compute_macd`, …) to the existing `indicators.compute()` call, plus future tools from Phase 7 (`run_backtest`, `optimize_params`, `walk_forward`, `monte_carlo`, `render_report`).
3. WebSocket route: `WS /api/sessions/{sid}/stream` — sends frames `{type:'text'|'tool_call'|'tool_result'|'done', ...}`.
4. Persist each assistant/tool turn to `messages` table.
5. Frontend: replace static [MessageList.tsx](src/components/chat/MessageList.tsx) with a live streaming view; render tool-call cards (collapsible) and tool-result summaries.

**Done when**: user says "compute RSI(14) on my BTC dataset" and gets a live streamed response with a tool-call card showing the RSI values.

---

### Phase 7 — Backtest + Optimize + Validation
**Goal**: core of the product — VectorBT + walk-forward + Monte Carlo, exposed as AI tools.

**Build steps**:
1. `pip install vectorbt ta-lib numba`
2. `backend/app/strategies.py` — a safe strategy runner that accepts a **constrained** strategy spec (JSON: entries, exits, position sizing, stop-loss, take-profit — NOT arbitrary Python) and returns a VectorBT `Portfolio`.
3. `backend/app/backtest.py` — `run_backtest(dataset_id, strategy_spec, fees=0.001, slippage=0.0005)`: loads parquet, builds indicators, runs VectorBT, returns metrics + equity curve + trade list.
4. `backend/app/optimize.py` — parameter grid sweep (e.g., RSI period × threshold) returning a heatmap of Sharpe/return.
5. `backend/app/validate.py` — walk-forward (rolling windows) + Monte Carlo (resample returns 1000×, report 5th/50th/95th percentile).
6. `backend/app/scoring.py` — composite score = w1·Sharpe + w2·(1−maxDD) + w3·winRate − w4·overfit_gap.
7. Register new tools in [tools.py](backend/app/tools.py): `run_backtest`, `optimize_params`, `walk_forward`, `monte_carlo`, `score_strategy`.
8. Add route: `POST /api/datasets/{did}/backtest` (also callable directly for UI).

**Done when**: AI can execute the 10-step flow from a natural-language prompt and return structured metrics.

---

### Phase 8 — Reports (HTML + PDF artifacts)
**Goal**: renders a polished report in the right artifacts pane after each backtest.

**Build steps**:
1. `backend/app/reports/templates/` — Jinja2 templates: cover, metrics summary, equity curve (Plotly JSON), drawdown, trade list, walk-forward heatmap, Monte Carlo fan chart.
2. `backend/app/reports/render.py` — builds the HTML bundle from the Portfolio object, writes to `workspaces/<pid>/reports/<report_id>.html`.
3. `pip install playwright && playwright install chromium` for PDF export.
4. Route: `GET /api/reports/{rid}` (HTML), `GET /api/reports/{rid}.pdf`.
5. Add tool `render_report(backtest_id) -> report_id`.
6. Frontend: [ArtifactsPane.tsx](src/components/ArtifactsPane.tsx) loads an iframe to the HTML report; Download button exports PDF.

**Done when**: after a backtest, artifact pane auto-opens to a styled HTML report and PDF download works.

---

### Phase 9 — Auto-memory subsystem
**Goal**: each workspace accumulates a memory folder of learnings from past conversations (what data was used, which strategies failed, user preferences), loaded as context in future sessions — mirroring Claude Code's own memory model.

**Build steps**:
1. `backend/app/memory/summarizer.py` — uses a **cheap model** (Haiku or local Llama, never the user's main model). Runs after every N messages OR at session close.
2. Writes atomic memory files to `workspaces/<pid>/memory/*.md` with frontmatter (name, description, type: user/feedback/project/reference) and maintains a `MEMORY.md` index.
3. Loader: prepends relevant memory files to the system prompt (rank by embedding similarity or topic tags).
4. Routes: `GET /api/projects/{pid}/memory`, `DELETE /api/projects/{pid}/memory/{file}`.
5. UI: a "Memory" tab in the sidebar to view/edit/delete memory files.

**Done when**: starting a new session on an existing project, the AI references prior decisions from that project's memory.

---

### Phase 10 — License + auto-update + installer
**Goal**: ship a paid, signed Windows installer with auto-update and license-key enforcement.

**Build steps**:
1. **Decide first** (user has deferred): license hosting (self-host vs Keygen / Paddle / Lemon Squeezy) and pricing tiers (Free + Pro + Team vs single tier vs lifetime).
2. `electron-builder` config for Windows NSIS installer + code signing.
3. License validator: on first launch, user enters key → app calls license server → caches signed token locally (7-day offline grace).
4. `electron-updater` wired to a release server (GitHub Releases or self-hosted).
5. Tier gating in UI (feature flags based on license tier).

**Done when**: a fresh Windows machine installs the `.exe`, activates with a license key, and receives an auto-update notification on next release.

---

## 8. UI pixel-match requirement (critical rule)

The user has explicitly rejected "loose" Claude Code–style UI. Hard requirement: any UI screen built must **visually match the actual Claude Code desktop app**.

Rules:
1. Before building any new UI screen, request a screenshot of the Claude Code counterpart if not already provided.
2. Background color must be near-black (≈ `#0d0d0d`), not gray (`#1a1a1a` was rejected).
3. Sidebar must have 5 layers: icon toolbar, tab pills, flat nav, pinned, project→session tree, user row at bottom.
4. Data model = Projects contain Sessions (chats), not flat workspaces.
5. Main header has breadcrumb dropdowns; input is a large pill with "Type / for commands"; footer has Ask-permissions toggle + model picker; artifacts pane is toggleable (not fixed).
6. When in doubt about a screen (settings, provider picker, routines, customize), **ask the user for a screenshot** before guessing.

---

## 9. Collaboration rules (user preferences)

- **Language**: user writes in **Hinglish** (Hindi + English mixed, Roman script). Respond in the same register — keep technical terms in English, flow words in Hinglish ("pehle", "phir", "theek hai").
- **Plan before build**: no code gets written until the user has reviewed a plan and said "go". Even placeholder files, scaffolds, or `package.json` entries need approval. User quote: *"don't build any think first understand what i want"* and *"final locked plan banaunga aur tabhi build start karenge"*.
- **Dev loop**: user verifies UI in browser and expects real screenshots/comparisons when UI changes.

---

## 10. Expected final output (what "done" looks like)

An installed Windows app where the full flow below works end-to-end:

1. User double-clicks **StratForge AI** shortcut. App opens with sidebar (empty), center chat area, artifacts closed.
2. User clicks **+ New Project**, names it "BTC Mean Reversion". A session is auto-created.
3. User drags a `BTC_1H.csv` file into the sidebar. App shows rows, date range, OHLCV detected. Dataset becomes the active context.
4. User picks a provider: **Claude (subscription)** or **Anthropic API key** or **Ollama → llama3.1**. Picks model `claude-opus-4-7`.
5. User types: *"Backtest an RSI-oversold + MACD-crossover strategy on this data. Optimize RSI period 10–20 and threshold 20–35. Walk-forward with 70/30 splits and run Monte Carlo."*
6. Assistant streams a plan, then tool-call cards appear one by one: `compute_rsi` → `compute_macd` → `run_backtest` → `optimize_params` → `walk_forward` → `monte_carlo` → `score_strategy` → `render_report`.
7. Artifacts pane auto-opens to a polished HTML report: cover, metrics (Sharpe 1.42, Max DD 8.3%, WinRate 54%, PF 1.61), equity curve, trade list, walk-forward heatmap, Monte Carlo fan.
8. User clicks **Download PDF** — Playwright renders and saves.
9. Next day, user opens the same project. The AI's memory already recalls the winning parameter set and suggests two variations to try — without re-explaining the context.
10. App auto-updates silently when Anthropic ships a new Claude version or a StratForge patch lands.

---

## 11. File map (as of this snapshot)

```
D:\ai-backtestingapp\
├── PROJECT_STATE.md              ← this file
├── StratForge_AI_Plan.pdf        ← original planning doc
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── index.html
├── .gitignore
│
├── electron\
│   ├── main.ts                   (window boot)
│   └── preload.ts
│
├── src\
│   ├── main.tsx
│   ├── App.tsx                   (3-pane layout)
│   ├── index.css
│   ├── components\
│   │   ├── ChatPane.tsx
│   │   ├── ArtifactsPane.tsx
│   │   ├── Sidebar.tsx
│   │   ├── NewProjectDialog.tsx
│   │   ├── chat\                 (MainHeader, MessageList, ChatInput, ChatFooter, ModelPicker)
│   │   ├── shell\                (TitleBar)
│   │   ├── sidebar\              (Nav, Tabs, Projects, Pinned, UserRow, UserMenuPopup)
│   │   └── ui\                   (Popup, Toast)
│   ├── store\
│   │   └── useAppStore.ts
│   └── lib\
│       ├── api.ts
│       ├── cn.ts
│       └── utils.ts
│
└── backend\
    ├── main.py                   (Uvicorn entry)
    ├── requirements.txt
    ├── smoke_btc.csv             (500-row test fixture)
    └── app\
        ├── __init__.py           (FastAPI factory)
        ├── paths.py
        ├── schemas.py
        ├── storage.py
        ├── data.py
        ├── indicators.py         (15 indicators)
        ├── tools.py              (auto-generated tool schemas)
        └── routes.py
```

Workspace data (per project) lives outside the repo at:
`%APPDATA%\StratForge\workspaces\<pj_id>\{data/, reports/, memory/, chats.db, workspace.json}`

---

## 12. Deferred / open questions (must resolve before their phase starts)

| Question | Blocks | Owner |
|----------|--------|-------|
| Claude Code OAuth device-flow endpoints — still available to 3rd-party apps? | Phase 5 | user must confirm |
| License hosting: self-host vs Keygen vs Paddle vs Lemon Squeezy? | Phase 10 | user decision |
| Pricing tiers: Free+Pro+Team vs single tier vs lifetime? | Phase 10 | user decision |
| Active dataset scope: session-scoped or project-scoped? | Phase 3.5 | decide at start of P3.5 |
| Strategy-spec schema: JSON-constrained DSL vs sandboxed Python? (Security vs flexibility) | Phase 7 | decide at start of P7 |

---

## 13. Next recommended slice

**Phase 3.5 — Dataset UI** (described in §7). Backend is ready and smoke-tested; the only reason a user cannot upload data from the app today is that no UI exists for it. Finishing this closes Phase 3 and unblocks a meaningful demo even before AI providers land.

Ask the user before starting: confirm Phase 3.5 first, or prioritize Phase 4 (providers) so chat can respond?
