# 📚 Vibe-Trading: Complete Codebase Study

**Repo:** https://github.com/HKUDS/Vibe-Trading
**Version:** 0.1.7 (as of 2026-05-06)
**License:** MIT
**Publisher:** HKUDS (Hong Kong University — Data Science group)
**Package:** `pip install vibe-trading-ai`

A comprehensive technical deep-dive into the Vibe-Trading codebase — an AI-powered multi-agent finance research workspace.

---

## 1. Project Overview

### 1.1 What Is Vibe-Trading?

**Vibe-Trading is an AI-powered multi-agent finance workspace** that turns natural-language requests into executable trading strategies, research insights, and portfolio analysis across global markets. It is *not* a live trading platform — it's a research/backtesting/analysis toolkit positioned as "your personal trading agent."

### 1.2 Core Value Proposition

> "One command to empower your agent with comprehensive trading capabilities."

The project pitches three distribution models:
1. **Standalone app** (`pip install vibe-trading-ai` → CLI + Web UI)
2. **MCP plugin** (plug into Claude Desktop / Cursor / OpenClaw via `vibe-trading-mcp`)
3. **SDK library** (import `backtest.engines` directly in other Python projects)

### 1.3 Key Numbers (headline features)

| Metric | Count | What it means |
|--------|-------|---------------|
| **Finance skills** | 74 | Specialized capability docs in 8 categories |
| **Swarm presets** | 29 | Pre-built multi-agent team workflows |
| **Agent tools** | 27 | Low-level actions the ReAct agent can call |
| **MCP tools** | 22 | Subset exposed to external MCP clients |
| **Backtest engines** | 7 + composite | China A / Global Equity / Crypto / ChinaFutures / GlobalFutures / Forex / Options + cross-market |
| **Data loaders** | 6 | tushare, yfinance, okx, akshare, ccxt, futu |
| **LLM providers** | 13 | OpenRouter, OpenAI, Codex OAuth, DeepSeek, Gemini, Groq, Qwen, Zhipu, Kimi, MiniMax, MIMO, Z.ai, Ollama |
| **Portfolio optimizers** | 4 | MVO, Equal Vol, Max Diversification, Risk Parity |

### 1.4 Tech Stack

**Backend (Python 3.11+):**
- **Framework:** FastAPI + uvicorn + SSE streaming
- **Agent orchestration:** LangChain + LangGraph + LangChain-OpenAI
- **MCP:** fastmcp (stdio + SSE transports)
- **Data/compute:** pandas 2.x, numpy, scipy, duckdb, scikit-learn
- **Market data:** yfinance, akshare, tushare, ccxt, futu-api
- **Reports:** jinja2 + matplotlib + weasyprint (HTML → PDF)
- **CLI UX:** rich (tables/panels) + prompt_toolkit (interactive TUI)

**Frontend (React 19):**
- **Framework:** React 19, TypeScript 5, Vite 6
- **Routing:** react-router-dom 7 (with lazy-loaded pages)
- **State:** Zustand 5
- **UI:** TailwindCSS 3 + @tailwindcss/typography
- **Charts:** ECharts 6 (heatmaps, equity curves, correlation matrices)
- **Markdown:** react-markdown + remark-gfm + rehype-highlight
- **Notifications:** sonner
- **Icons:** lucide-react

**DevOps:**
- Multi-stage Dockerfile (node:20 frontend build → python:3.11-slim runtime)
- docker-compose with named volumes for persistent runs/sessions
- GitHub Actions workflows
- Dev containers via `.devcontainer/devcontainer.json`

---

## 2. Repository Structure

```
Vibe-Trading/
├── agent/                          # Python backend (the heart of the app)
│   ├── cli.py                      # 2193-line CLI — interactive TUI + subcommands
│   ├── api_server.py               # FastAPI server (runs, sessions, upload, swarm, SSE, settings)
│   ├── mcp_server.py               # MCP server — 22 tools via fastmcp
│   ├── requirements.txt            # Explicit pip deps
│   ├── SKILL.md                    # MCP manifest / skill definition
│   ├── .env.example                # LLM provider templates for 13 providers
│   ├── src/
│   │   ├── agent/                  # ReAct ReAct agent core
│   │   │   ├── loop.py             # AgentLoop — 5-layer compression + read/write batching
│   │   │   ├── context.py          # System prompt builder + memory recall injection
│   │   │   ├── skills.py           # SkillsLoader — reads 74 SKILL.md files
│   │   │   ├── tools.py            # BaseTool + ToolRegistry abstractions
│   │   │   ├── memory.py           # Per-run workspace memory
│   │   │   ├── frontmatter.py      # Shared YAML frontmatter parser
│   │   │   └── trace.py            # JSONL execution trace writer
│   │   │
│   │   ├── core/
│   │   │   ├── runner.py           # Legacy entry point
│   │   │   └── state.py            # RunStateStore — manages runs/ dir
│   │   │
│   │   ├── memory/
│   │   │   └── persistent.py       # PersistentMemory — ~/.vibe-trading/memory/
│   │   │
│   │   ├── session/                # Multi-turn chat sessions + FTS5 search
│   │   │   ├── events.py
│   │   │   ├── models.py           # Session, Message Pydantic models
│   │   │   ├── search.py           # SQLite FTS5 full-text search
│   │   │   ├── service.py          # Session CRUD
│   │   │   └── store.py            # File persistence
│   │   │
│   │   ├── providers/              # LLM abstraction
│   │   │   ├── chat.py             # ChatLLM (tool calling + streaming)
│   │   │   ├── llm.py              # build_llm() factory
│   │   │   ├── openai_codex.py     # Codex ChatGPT OAuth adapter
│   │   │   └── llm_providers.json  # 13 provider definitions
│   │   │
│   │   ├── shadow_account/         # FLAGSHIP: Extract user's own strategy from broker journal
│   │   │   ├── extractor.py        # Distill 3-5 if-then rules from profitable trades
│   │   │   ├── codegen.py          # Generate signal_engine.py from rules
│   │   │   ├── backtester.py       # Multi-market backtest of shadow
│   │   │   ├── reporter.py         # 8-section HTML/PDF report
│   │   │   ├── scanner.py          # Today's matching signals
│   │   │   ├── storage.py          # JSON persistence at ~/.vibe-trading/shadow_accounts/
│   │   │   ├── fonts.py
│   │   │   └── templates/          # Jinja2 HTML + CSS for report
│   │   │
│   │   ├── swarm/                  # Multi-agent DAG orchestration
│   │   │   ├── runtime.py          # SwarmRuntime — topological layers + ThreadPoolExecutor
│   │   │   ├── presets.py          # YAML preset loader + DAG validator
│   │   │   ├── models.py           # SwarmRun, SwarmTask, SwarmAgentSpec Pydantic
│   │   │   ├── worker.py           # Single-agent worker (runs AgentLoop)
│   │   │   ├── mailbox.py          # Inter-agent message passing
│   │   │   ├── store.py            # Run persistence
│   │   │   ├── task_store.py       # Task-level persistence + topological_layers()
│   │   │   ├── api_models.py       # REST API models
│   │   │   └── presets/            # 29 YAML files — each defines agents + DAG
│   │   │
│   │   ├── skills/                 # 74 skill directories (each = SKILL.md + optional examples.md)
│   │   │   ├── strategy-generate/   (Strategy)
│   │   │   ├── candlestick/
│   │   │   ├── ichimoku/
│   │   │   ├── smc/
│   │   │   ├── harmonic/
│   │   │   ├── elliott-wave/
│   │   │   ├── chanlun/
│   │   │   ├── ml-strategy/
│   │   │   ├── technical-basic/
│   │   │   ├── ...                 (see §4.3 for full list)
│   │   │
│   │   ├── tools/                  # 27 agent tool implementations
│   │   │   ├── backtest_tool.py
│   │   │   ├── bash_tool.py
│   │   │   ├── read_file_tool.py / write_file_tool.py / edit_file_tool.py
│   │   │   ├── remember_tool.py    # Cross-session memory save/recall/forget
│   │   │   ├── skill_writer_tool.py  # Self-evolving skills (CRUD)
│   │   │   ├── session_search_tool.py # FTS5 search across past sessions
│   │   │   ├── swarm_tool.py       # Agents can spawn swarms
│   │   │   ├── web_search_tool.py  # DuckDuckGo
│   │   │   ├── web_reader_tool.py  # URL → Markdown
│   │   │   ├── doc_reader_tool.py  # PDF/DOCX/XLSX/PPT/images
│   │   │   ├── factor_analysis_tool.py  # IC/IR + quantile backtest
│   │   │   ├── options_pricing_tool.py  # Black-Scholes + Greeks
│   │   │   ├── pattern_tool.py     # Chart pattern detection
│   │   │   ├── compact_tool.py     # Model-triggered context compression
│   │   │   ├── background_tools.py # Async job management
│   │   │   ├── shadow_account_tool.py
│   │   │   ├── trade_journal_tool.py + trade_journal_parsers.py
│   │   │   ├── load_skill_tool.py
│   │   │   └── path_utils.py       # Security sandbox for file I/O
│   │   │
│   │   ├── preflight.py            # Startup checks (API key, deps, disk space)
│   │   └── ui_services.py          # Web UI helpers
│   │
│   ├── backtest/                   # SDK layer — engines + loaders + optimizers
│   │   ├── runner.py               # python -m backtest.runner <run_dir>
│   │   ├── metrics.py              # Sharpe, Sortino, Calmar, IR, max drawdown, etc.
│   │   ├── validation.py           # Monte Carlo + Bootstrap CI + Walk-Forward
│   │   ├── benchmark.py            # SPY / CSI 300 auto-benchmark
│   │   ├── correlation.py          # Rolling correlation heatmap
│   │   ├── models.py               # Position, Trade, EquitySnapshot dataclasses
│   │   ├── engines/
│   │   │   ├── base.py             # BaseEngine — shared bar-by-bar loop
│   │   │   ├── china_a.py          # A-share specific rules (T+1, 10% limit)
│   │   │   ├── china_futures.py
│   │   │   ├── crypto.py
│   │   │   ├── forex.py
│   │   │   ├── futures_base.py     # Shared futures logic
│   │   │   ├── global_equity.py    # US + HK
│   │   │   ├── global_futures.py
│   │   │   ├── composite.py        # Cross-market (shared capital pool)
│   │   │   ├── options_portfolio.py
│   │   │   └── _market_hooks.py    # Market-specific hook points
│   │   ├── loaders/
│   │   │   ├── base.py             # DataLoader Protocol
│   │   │   ├── registry.py         # Loader registry + FALLBACK_CHAINS
│   │   │   ├── akshare_loader.py
│   │   │   ├── yfinance_loader.py
│   │   │   ├── okx.py
│   │   │   ├── ccxt_loader.py
│   │   │   ├── tushare.py
│   │   │   └── futu.py
│   │   └── optimizers/
│   │       ├── base.py
│   │       ├── mean_variance.py    # Markowitz MVO
│   │       ├── risk_parity.py
│   │       ├── equal_volatility.py
│   │       └── max_diversification.py
│   │
│   └── tests/                      # ~50 test files (pytest)
│       ├── test_akshare_loader.py
│       ├── test_china_a_engine.py
│       ├── test_security_auth_api.py    # Security regression tests
│       ├── test_path_safety.py
│       ├── test_file_tool_sandbox_security.py
│       ├── test_swarm_preset_inspect.py
│       ├── test_persistent_memory.py
│       └── ... (40+ more)
│
├── frontend/                       # React 19 + Vite + TypeScript
│   └── src/
│       ├── pages/                  # Home, Agent, RunDetail, Compare, Settings, Correlation
│       ├── components/
│       │   ├── charts/             # ECharts wrappers
│       │   ├── chat/               # Agent chat UI
│       │   ├── common/             # ErrorBoundary, shared widgets
│       │   └── layout/             # Layout shell
│       ├── hooks/
│       │   ├── useSSE.ts           # Server-Sent Events client
│       │   └── useDarkMode.ts
│       ├── lib/
│       │   ├── api.ts              # Backend API client
│       │   ├── apiAuth.ts          # API_AUTH_KEY handling
│       │   ├── chart-theme.ts
│       │   ├── echarts.ts          # ECharts lazy loader
│       │   ├── formatters.ts
│       │   ├── i18n.tsx            # Multi-language provider
│       │   ├── indicators.ts
│       │   └── utils.ts
│       ├── stores/
│       │   └── agent.ts            # Zustand store (runs, sessions, messages)
│       ├── types/agent.ts
│       ├── main.tsx                # React root + ErrorBoundary + I18n + Toaster
│       ├── router.tsx              # Lazy-loaded routes
│       ├── index.css
│       └── App.tsx (not present — Layout is the shell)
│
├── Dockerfile                      # Multi-stage: frontend-build → python-runtime
├── docker-compose.yml              # Named volumes + optional frontend profile
├── pyproject.toml                  # Package metadata + CLI entry points
├── README.md (+ README_zh/ja/ko/ar.md)  # 782-line main doc + 4 translations
├── CONTRIBUTING.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── MANIFEST.in                     # Package data inclusion
├── LICENSE                         # MIT
├── .github/
│   ├── workflows/                  # CI pipelines
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── .devcontainer/devcontainer.json # VS Code dev container
├── assets/                         # Logos, scene screenshots, demo MP4s
├── docs/                           # Session docs (currently only 1 PR session note)
└── scripts/dev                     # Dev shell script
```

---

## 3. Backend / Agent Code Deep-Dive

### 3.1 Entry Points (3)

The `pyproject.toml` registers three CLI commands:

```toml
[project.scripts]
vibe-trading = "cli:main"              # Interactive TUI + subcommands
vibe-trading-mcp = "mcp_server:main"   # MCP stdio server
# vibe-trading serve lives inside cli.py and delegates to api_server.serve_main
```

### 3.2 The ReAct Agent Core (`agent/src/agent/loop.py`)

**AgentLoop** is the heart. It's a ReAct loop with five layers of context compression — this is Vibe-Trading's most technically impressive piece.

#### Five-Layer Context Compression

| Layer | Trigger | Method | API cost |
|-------|---------|--------|----------|
| **L1: microcompact** | Every iteration | Silently prunes old tool results, keeping most recent 3 | Zero |
| **L2: context_collapse** | Tokens > 70% of threshold | Folds long text blocks: keeps head (900 chars) + tail (500 chars), drops middle | Zero |
| **L3: auto_compact** | Tokens > 40k | LLM structured summary using fixed template (Goal / Progress / Decisions / Files / Pending) | 1 LLM call |
| **L4: compact tool** | Model explicitly calls `compact` | Triggers L3 with optional focus topic | 1 LLM call |
| **L5: iterative update** | Nth compression | Updates previous summary instead of starting fresh → zero info decay | 1 LLM call |

#### Read/Write Tool Batching

Another clever optimization:
- Consecutive **readonly** tools run in parallel via `ThreadPoolExecutor(max_workers=8)`
- **Write** tools run serially between readonly batches
- `BaseTool.is_readonly` flag determines batching

This means when the model wants to read 5 files + compute 3 indicators simultaneously, they all run in parallel, dramatically cutting latency on fan-out queries.

#### Tool Pair Repair

After compression, orphaned `tool_call` without a `tool_result` (or vice-versa) would break the OpenAI API. `_fix_tool_pairs()` walks the message list and:
1. Removes tool results whose matching call was compressed away
2. Inserts stub results (`"[Result from earlier context — see summary above]"`) for calls whose results were compressed

#### Key Invariants
- `max_iterations=50` (configurable)
- Duplicate-call suppression: if a tool already succeeded (`self._called_ok`), retries return a skip message unless `repeatable=True`
- `run_dir` normalization: relative `run_dir` args (like `"."`) are resolved against the active run dir
- Background task notifications injected between iterations

### 3.3 System Prompt Architecture (`agent/src/agent/context.py`)

The system prompt is **dynamically composed** from:
1. Tool descriptions (auto-generated from tool `parameters` JSON Schema)
2. Skill summaries (74 one-liners from SKILL.md frontmatter)
3. Workspace state summary (active run_dir, files, etc.)
4. **Persistent memory snapshot** — frozen at session start (preserves prompt cache!)
5. Current date/time

The prompt has a **Task Routing** section that maps intent keywords to workflows:

| Intent | Workflow |
|--------|----------|
| Backtest | load_skill("strategy-generate") → write config.json → write signal_engine.py → `backtest()` |
| Swarm team | `run_swarm(prompt=...)` (only when user explicitly asks) |
| Factor / options / research | Skill-guided analysis |
| Document / web | `read_document` / `read_url` |
| Trade journal | `load_skill("trade-journal")` → `analyze_trade_journal` |
| Shadow Account | `load_skill("shadow-account")` → extract → backtest → render |

#### Auto-Recall Memory Injection

On every user message, `build_messages()` scans persistent memory via `find_relevant(query)` and injects the top 3 matches as `<recalled-memories>` XML tags into the user message. This is a **retrieval layer** that's separate from the frozen system-prompt snapshot — keeping the system prompt cacheable while still surfacing context.

### 3.4 Tool System (`agent/src/agent/tools.py` + `agent/src/tools/`)

**BaseTool** abstract class exposes:
- `name`, `description`, `parameters` (JSON Schema), `repeatable`, `is_readonly`
- `check_available()` classmethod (dependency check — excludes tool from registry if fails)
- `execute(**kwargs) → str` (always returns JSON string)
- `to_openai_schema()` (OpenAI function calling format)

**ToolRegistry** collects registered tools, auto-generates OpenAI tool definitions, and wraps exceptions in `{"status": "error", "error": str(exc)}` JSON.

**`build_registry()`** (`agent/src/tools/__init__.py`) auto-discovers tools, respects `check_available()`, and has an `include_shell_tools` flag — critical security boundary for remote MCP/API deployments.

#### The 27 Tools (grouped)

| Group | Tools |
|-------|-------|
| **Backtest** | `backtest`, `factor_analysis`, `options_pricing`, `pattern` |
| **File I/O** | `read_file`, `write_file`, `edit_file` (sandboxed via `path_utils`) |
| **Shell** | `bash`, `background_run`, `check_background` (shell-gated) |
| **Web** | `web_search` (DuckDuckGo), `web_reader` (URL→Markdown), `read_document` |
| **Agent infra** | `load_skill`, `save_skill`, `patch_skill` (self-evolving!), `delete_skill`, `file_skill` |
| **Memory** | `remember`, `forget`, `session_search` (FTS5) |
| **Compression** | `compact` (L4 trigger) |
| **Orchestration** | `run_swarm` (agents spawn agents!) |
| **Shadow Account** | `extract_shadow_strategy`, `run_shadow_backtest`, `render_shadow_report`, `scan_shadow_signals` |
| **Trade Journal** | `analyze_trade_journal` |

### 3.5 Skills System (74 skills, 8 categories)

Each skill is a **self-contained markdown knowledge document**:

```
agent/src/skills/strategy-generate/
├── SKILL.md           # Main doc with YAML frontmatter
└── examples.md        # Optional code examples
```

Frontmatter example:
```yaml
---
name: strategy-generate
description: Create, modify, and optimize quantitative trading strategies, then backtest and evaluate them.
category: strategy
---
```

**`SkillsLoader`** scans all `agent/src/skills/*/SKILL.md` files on init, and exposes:
- `get_descriptions()` — one-liner summary injected into system prompt
- `get_content(name)` — full doc loaded on-demand via `load_skill` tool

This achieves **lazy loading**: the system prompt stays small (74 one-liners ≈ few KB), and full methodology docs are fetched only when the agent actually needs them.

#### Category Breakdown

| Category | Count | Examples |
|----------|-------|----------|
| Data Source | 6 | data-routing, tushare, yfinance, okx-market, akshare, ccxt |
| Strategy | 17 | strategy-generate, cross-market-strategy, candlestick, ichimoku, elliott-wave, smc, chanlun, harmonic, multi-factor, ml-strategy, pair-trading, pine-script, vnpy-export |
| Analysis | 17 | factor-research, macro-analysis, global-macro, valuation-model, earnings-forecast, credit-analysis, dividend-analysis, behavioral-finance, minute-analysis, quant-statistics |
| Asset Class | 9 | options-strategy, options-advanced, convertible-bond, etf-analysis, asset-allocation, sector-rotation, commodity-analysis, fund-analysis |
| Crypto | 7 | perp-funding-basis, liquidation-heatmap, stablecoin-flow, defi-yield, onchain-analysis, crypto-derivatives, token-unlock-treasury |
| Flow | 7 | hk-connect-flow, us-etf-flow, edgar-sec-filings, financial-statement, adr-hshare, corporate-events, earnings-revision |
| Tool | 10 | backtest-diagnose, report-generate, pine-script, doc-reader, web-reader, vnpy-export, market-microstructure, execution-model, trade-journal, shadow-account |
| Risk | 1 | ashare-pre-st-filter (A-share ST/*ST risk screening) |

#### Self-Evolving Skills

Users/agents can **create new skills** via the `save_skill` tool. Files land at `agent/src/skills/<user-created>/SKILL.md`. Additional tools exist for CRUD:
- `save_skill` — create new skill
- `patch_skill` — modify existing
- `delete_skill` — remove
- `file_skill` — list/get by name

This combined with **OpenSpace integration** (mentioned in README) lets the entire skill library evolve across users via a community platform (open-space.cloud).

### 3.6 Multi-Agent Swarm System (`agent/src/swarm/`)

Vibe-Trading's **swarm** is a DAG-based multi-agent orchestrator. Each "swarm preset" is a YAML file defining:
1. A set of agents (each with its own system prompt, tool whitelist, skill whitelist, timeouts, retries, optional model override)
2. A set of tasks (each bound to an agent, with `depends_on` edges and `input_from` mapping for upstream context)
3. User variables (templated into prompts via Python `.format()`)

#### The 29 Presets

| Preset | Agents | Purpose |
|--------|--------|---------|
| `investment_committee` | 4 | Bull/bear debate → risk review → PM final call |
| `global_equities_desk` | 4+ | A-share + HK/US + crypto → global strategist |
| `crypto_trading_desk` | 4+ | Funding/basis + liquidation + flow → risk manager |
| `earnings_research_desk` | 4+ | Fundamentals + revisions + options → earnings strategist |
| `macro_rates_fx_desk` | 4+ | Rates + FX + commodity → macro PM |
| `quant_strategy_desk` | 5+ | Screening → factor research → backtest → risk audit |
| `technical_analysis_panel` | 5+ | Classic TA + Ichimoku + harmonic + Elliott + SMC → consensus |
| `risk_committee` | 3+ | Drawdown + tail risk + regime → sign-off |
| `global_allocation_committee` | | Cross-market allocation |
| `crypto_research_lab` | | Deep crypto research |
| `derivatives_strategy_desk` | | Options/futures |
| `ml_quant_lab` | | ML-driven quant |
| `pairs_research_lab` | | Stat arb pair trading |
| `statistical_arbitrage_desk` | | Stat arb |
| `sentiment_intelligence_team` | | Sentiment analysis |
| `social_alpha_team` | | Social media alpha |
| ...plus 13 more |

#### Execution Model (`SwarmRuntime`)

```
1. start_run(preset_name, user_vars) — builds SwarmRun from YAML
2. validate_dag() — checks for cycles, unknown references
3. Fork background daemon thread
4. topological_layers() — computes parallel layers
5. For each layer:
   a. Check cancel_event
   b. Submit all tasks in layer to ThreadPoolExecutor(max_workers=4)
   c. Emit layer_started event → SSE stream to UI
   d. Run worker with upstream_summaries injected via input_from mapping
   e. Retry on failure up to agent.max_retries
   f. Emit task_completed / task_failed events
6. Finalize: last task's summary becomes final_report
```

Each "worker" is just an isolated AgentLoop instance with a tool/skill whitelist scoped to that agent. Workers get **upstream summaries** as context — not full transcripts — which keeps token usage manageable.

#### Cross-thread Safety
- `run_worker_with_retries` cumulative token counting
- Layer-level deadline using `as_completed(timeout=deadline)` to defend against C-extension-blocked threads
- Manual `ThreadPoolExecutor` lifecycle (not `with`) so `KeyboardInterrupt` can bail cleanly via `shutdown(wait=False, cancel_futures=True)`

### 3.7 Backtest Engine (`agent/backtest/`)

#### The SignalEngine Contract

Every strategy is a `SignalEngine` class with a single method:

```python
class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """
        Args:
            data_map: code -> OHLCV DataFrame (DatetimeIndex + open/high/low/close/volume)
        Returns:
            code -> signal Series, value range [-1.0, 1.0]
            1.0 = fully long, 0.5 = half position, 0.0 = flat, -1.0 = fully short
        """
```

The agent writes this class to `<run_dir>/code/signal_engine.py`, and writes config to `<run_dir>/config.json`. The `backtest` tool then invokes `python -m backtest.runner <run_dir>`.

#### Security: AST Validation of signal_engine.py

Before importing user-generated code, `runner.py` parses the AST and **rejects executable top-level statements**:
- Only allowed at module level: imports, function defs, class defs, literal-only assignments, docstrings
- Decorators forbidden
- Non-literal function defaults forbidden
- Class bodies must contain only methods + literal assignments
- Unsafe annotations / base classes forbidden

This prevents malicious code injection through LLM-written strategies.

#### BaseEngine Execution Loop

All market engines inherit from `BaseEngine`. The shared `run_backtest()` flow:
1. Load data via loader
2. Generate signals via SignalEngine
3. Align signals to date index, shift by 1 bar (next-bar-open), normalize weights (`sum(abs) <= 1`)
4. Optional portfolio optimizer (MVO / RP / EVV / MaxDiv)
5. Bar-by-bar execution loop:
   - `on_bar()` hook (funding fees, liquidation for crypto/futures)
   - `can_execute()` check (market rule — e.g. A-share limit-up blocks sells)
   - `round_size()` per lot rules
   - `calc_commission()` per fee structure
   - `apply_slippage()` per slippage model
   - Record `EquitySnapshot`
6. Force close on last bar
7. Compute metrics (Sharpe, Sortino, Calmar, max DD, win rate, profit factor, etc.)
8. Optional **Validation** (`validation.py`):
   - **Monte Carlo** — randomize trade order, percentile distribution of final returns
   - **Bootstrap CI** — resample trades for 95% CI on Sharpe
   - **Walk-Forward** — rolling train/test split to measure out-of-sample decay
9. External benchmark fetch (`benchmark.py`) — auto-selects SPY / CSI 300 / BTC based on strategy codes
10. Write artifacts: `equity.csv`, `positions.csv`, `trades.csv`, `metrics.csv`, `ohlcv_<code>.csv`, optional `validation.json`

#### Market Engines

| Engine | Market rules |
|--------|--------------|
| `china_a.py` | T+1 settlement, 10% daily limit, no intraday short, pre-ST filter |
| `china_futures.py` | Contract multipliers, overnight margin, exchange-specific |
| `global_equity.py` | US + HK, T+0, short allowed |
| `crypto.py` | 24/7, funding rate, leverage, liquidation |
| `forex.py` | Pip-based pricing, rollover swap |
| `global_futures.py` | CME/ICE/EUREX — tick size, margin |
| `options_portfolio.py` | Greeks, expiry, BSM pricing |
| `composite.py` | Cross-market — shared capital pool across A-shares + HK/US + crypto simultaneously |

#### Data Loader Registry (`loaders/registry.py`)

```python
LOADER_REGISTRY = {
    "tushare": TushareLoader,
    "yfinance": YFinanceLoader,
    "okx": OKXLoader,
    "akshare": AkshareLoader,
    "ccxt": CCXTLoader,
    "futu": FutuLoader,
}

FALLBACK_CHAINS = {
    "a_share":    ["tushare", "akshare", "futu"],
    "us_equity":  ["yfinance", "akshare"],
    "hk_equity":  ["yfinance", "akshare", "futu"],
    "crypto":     ["okx", "ccxt"],
    "futures":    ["akshare", "tushare"],
    "forex":      ["akshare", "yfinance"],
}
```

With `source="auto"`, codes are auto-detected by regex pattern and routed to the right loader. If the primary fails (e.g. Tushare rate-limited), the engine walks down the fallback chain at runtime. This is how "zero config" multi-market works.

### 3.8 Shadow Account (Flagship Feature)

A unique feature that *no other AI trading agent has*. The flow:

1. **`analyze_trade_journal(file_path)`**
   - Parses broker CSV/Excel (同花顺, 东财, 富途, generic formats)
   - Auto-detects encoding
   - Computes profile: holding days, win rate, PnL ratio, top symbols, hourly distribution
   - Computes 4 behavior diagnostics:
     - **Disposition effect** (holding losers too long)
     - **Overtrading** (excessive frequency)
     - **Chasing momentum** (buying high after price spike)
     - **Anchoring** (buying near prior peaks)

2. **`extract_shadow_strategy(journal_path)`**
   - Analyzes profitable roundtrips only
   - Distills **3-5 human-readable if-then rules** (in Chinese)
   - Stores `ShadowProfile` with rules, support counts, coverage rates, sample trades

3. **`run_shadow_backtest(shadow_id, markets=["china_a","hk","us","crypto"])`**
   - Generates `signal_engine.py` from the rules via **codegen**
   - Runs the shadow against multi-market data
   - Computes **delta-PnL attribution vs user's realized trades** (i.e. "what if you had followed your own winning rules consistently?")

4. **`render_shadow_report(shadow_id)`**
   - 8-section HTML/PDF with matplotlib charts + weasyprint PDF conversion
   - Key section: **"You vs Shadow"** showing how much money the user left on the table from rule violations, early exits, missed signals

5. **`scan_shadow_signals(shadow_id)`**
   - Lists today's symbols across all markets matching the shadow's entry cadence
   - Disclaimed as research-only, not trade recommendations

**Security:** Shadow Account codegen is AST-validated just like strategy-generate (prevents injection via rule parameters).

### 3.9 Persistent Memory (`agent/src/memory/persistent.py`)

File-based, zero external dependencies:

```
~/.vibe-trading/memory/
├── MEMORY.md                 # Index (< 200 lines)
├── user_user_prefs.md        # Entries with YAML frontmatter
├── project_btc.md
└── ...
```

Each entry has frontmatter:
```yaml
---
name: User RSI preference
description: User prefers RSI-based strategies with max 10% drawdown
type: user  # user | feedback | project | reference
---
```

**Design principle: frozen snapshot injected at session start.**
- Index file loaded once → system prompt
- Subsequent `add()` / `remove()` update files but **do not** change the snapshot
- Next session picks up updates
- Why: preserves OpenAI prompt caching (system prompt is stable)

**Retrieval:** `find_relevant(query)` uses keyword scoring:
- ASCII tokens `>= 3 chars` + CJK individual characters
- Score = metadata_hits × 2.0 + body_hits × 1.0
- Top 5 results injected into user message (not system prompt)

### 3.10 LLM Provider Abstraction

`agent/src/providers/llm_providers.json` lists 13 providers, each declaring:
- `api_key_env` / `base_url_env` — env var names
- `default_model`, `default_base_url`
- `api_key_required` — enables Ollama to work without key
- `auth_type` — `api_key` or `oauth` (Codex uses ChatGPT OAuth via `oauth-cli-kit`)

`build_llm(model_name)` builds a `ChatOpenAI` instance from LangChain, handling:
- Thinking/reasoning content preservation across Kimi, DeepSeek, Qwen
- Tool calling format normalization
- Streaming deltas via `stream_chat(..., on_text_chunk=cb)`

#### Recommended Model Tiers (from README)

| Tier | Examples | Purpose |
|------|----------|---------|
| Best | Claude Opus 4.7, Sonnet 4.6, GPT-5.4, Gemini 3.1 Pro | Complex swarms, paper-grade |
| Sweet spot (default) | DeepSeek v3.2, Grok 4.20, GLM 5.1, Kimi K2.5, Qwen3 Max | Daily driver |
| Avoid | `*-nano`, `*-flash-lite`, `*-coder-next` | Poor tool calling |

---

## 4. Frontend Deep-Dive

### 4.1 Architecture

- **React 19 StrictMode** + lazy-loaded routes (code-splitting cut bundle 688KB → 262KB per release notes)
- **Zustand** single `agent` store holding runs/sessions/messages
- **Server-Sent Events** (`useSSE.ts` hook) for streaming agent output — no WebSockets
- **API_AUTH_KEY** authentication layer (`apiAuth.ts`) — Bearer token injected into fetch requests
- **Multi-language** via custom `I18nProvider` (`lib/i18n.tsx`)
- **ErrorBoundary** wraps the entire router — catches render crashes
- **sonner** for toast notifications
- **react-markdown + remark-gfm + rehype-highlight** for rendering agent responses

### 4.2 Pages (6)

| Page | Purpose |
|------|---------|
| `Home.tsx` | Hero landing with 4 feature cards, links to /agent |
| `Agent.tsx` | Chat interface with SSE streaming, tool cards, skill panel |
| `RunDetail.tsx` | Single run: metrics table, equity chart, trades, benchmark comparison |
| `Compare.tsx` | Multi-run comparison |
| `Correlation.tsx` | Rolling correlation heatmap (ECharts) |
| `Settings.tsx` | LLM provider + model + reasoning effort + data source credentials |

### 4.3 Key UX Details

- **Lazy loading**: all pages are `lazy()` with a generic `PageLoader` fallback
- **Settings reads are side-effect free**: `GET /settings/llm` never creates `.env`
- **Loopback trust**: dev mode works without `API_AUTH_KEY` on localhost; required for remote
- **Dark mode**: `useDarkMode.ts` hook, Tailwind class toggle

---

## 5. DevOps & Configuration

### 5.1 Docker

**Multi-stage build:**
- Stage 1: `node:20-slim` builds frontend to `/app/frontend/dist`
- Stage 2: `python:3.11-slim` installs agent + copies built dist
- **Non-root user** (`vibe`) for security
- Default port `127.0.0.1:8899` (localhost-only!) — forces conscious opt-in for network exposure
- Health check hits `/health` endpoint

**docker-compose.yml:**
- Named volumes for `runs/` and `sessions/` (persistent across container restarts)
- Optional `frontend` profile for dev mode (hot reload)
- `VIBE_TRADING_TRUST_DOCKER_LOOPBACK=1` flag for container networking

### 5.2 Security Boundaries

Vibe-Trading has **aggressive security hardening** (recent v0.1.7 focus):

| Surface | Boundary |
|---------|----------|
| API | `API_AUTH_KEY` required for non-local clients (Bearer token) |
| Shell tools | Not exposed to remote API/MCP-SSE unless `VIBE_TRADING_ENABLE_SHELL_TOOLS=1` |
| File I/O | Sandboxed to `agent/uploads`, `agent/runs`, `./uploads`, `./data`, `~/.vibe-trading/*` — extendable via `VIBE_TRADING_ALLOWED_FILE_ROOTS` |
| Generated code | AST-validated before import (strategy-generate + shadow codegen) |
| Upload | Streamed in 1MB chunks with `MAX_UPLOAD_SIZE` cap |
| Docker | Non-root user, published on 127.0.0.1 by default |
| CORS | Explicit origin allowlist (not `*`) |
| Path traversal | `safe_path()` prevents `..` escapes |

Security credit: coordinated validation by `lemi9090 (S2W)` mentioned in README.

### 5.3 CI/CD

`.github/workflows/` (not read but inferred from README):
- pytest on all tests
- Ruff linting (line-length 120, target py311)
- PyPI publishing on tag

---

## 6. Key Innovations & Standout Features

### 6.1 Unique to Vibe-Trading

1. **Shadow Account** — "What your own winning rules would have made if you had followed them consistently" is a genuinely novel UX pattern. Combines journal analysis + rule extraction + multi-market backtest + attribution in one flow.

2. **29 pre-built swarm presets** — Most AI apps have "an agent." Vibe-Trading has 29 *named investment committees* ready to run (Investment Committee, Crypto Trading Desk, Risk Committee, etc.).

3. **74 skills as knowledge docs** — Instead of hardcoding methodology in system prompts, skills are lazily-loaded MD files. Makes the library extensible by non-coders and shareable via OpenSpace.

4. **5-layer context compression** — Most ReAct implementations have one compression strategy. Vibe-Trading layers microcompact → context_collapse (zero-cost) → auto_compact (LLM) → manual compact tool → iterative updates. This is genuinely sophisticated.

5. **Self-evolving skills** — Agents can create/patch/delete skills via tools. Means the system gets smarter across sessions without code changes.

6. **Cross-market composite backtest** — Shared capital pool across A-shares + HK/US + crypto simultaneously with per-market rules. Most backtesters are single-market.

7. **Multi-platform strategy export** — One command `/pine <run_id>` exports to TradingView Pine Script v6, TDX (Chinese charting), AND MetaTrader 5 (MQL5).

8. **AST-validated LLM-written code** — Before importing `signal_engine.py`, the runner parses AST and rejects any executable top-level statements. Defends against prompt-injection code execution.

### 6.2 Architectural Patterns Worth Studying

1. **Frozen memory snapshot** — Prompt caching optimization by separating frozen system-prompt memory from per-query auto-recall injection.

2. **Read/Write tool batching** — Consecutive readonly tools run in parallel, write tools serial. Cuts latency on fan-out queries dramatically.

3. **Runtime fallback chains** — Data loaders degrade gracefully (`tushare` → `akshare` → `futu`) without agent intervention.

4. **DAG swarm with topological layers** — Parallelism within layers, serial between. Classic but well-implemented.

5. **Tool registry with `check_available()`** — Tools self-report dependency availability and are excluded from the registry (and thus the system prompt) if prerequisites aren't met.

6. **Skill category hierarchy** — 74 skills in 8 categories with full-text descriptions in frontmatter enables semantic routing.

---

## 7. Comparison vs StratForge AI

Since this study is for comparison with our existing `StratForge AI` project:

### 7.1 Where Vibe-Trading is stronger

| Area | Vibe-Trading | StratForge AI |
|------|--------------|---------------|
| **Markets** | 6 data sources, 7+ engines, composite cross-market | Upload CSV/Excel only |
| **Skills library** | 74 MD skills with lazy loading | Handful of agents (8) with hardcoded prompts |
| **Multi-agent** | 29 named swarm presets, DAG orchestration, parallel layers | MasterAgent orchestrates 7 sub-agents linearly |
| **Context compression** | 5 layers including zero-cost layer 2 | None visible — relies on provider context window |
| **LLM providers** | 13 (including Codex OAuth, Ollama, Chinese providers) | Anthropic / OpenAI / Gemini / Ollama / Claude CLI |
| **Distribution** | CLI + Web UI + MCP plugin + PyPI package | Electron desktop app |
| **Security** | Dedicated CVE tracker, AST code validation, API_AUTH_KEY, sandbox | API keys in system keyring, sandboxed file paths |
| **Memory** | Persistent + session FTS5 search + auto-recall | In-session only |
| **Shadow Account** | Unique journal → rules → backtest → attribution flow | Not present |
| **Export** | Pine Script v6 + TDX + MT5 in one command | Pine Script v5 |
| **Swarm** | 29 named teams (investment committee, risk committee, etc.) | Ad-hoc agent roles |

### 7.2 Where StratForge AI is stronger

| Area | StratForge AI | Vibe-Trading |
|------|---------------|--------------|
| **UX polish** | Electron desktop app with custom title bar, split panes | Web UI (works but browser-based) |
| **Guided pipeline** | 8-stage stepper with visual progress | Agent decides stages freely |
| **Strategy Evolution** | Explicit genetic algorithm (crossover, mutation, elitism) over 5 generations | Agent "tries variants" but no named GA |
| **Critic Agent** | Aggressive institutional stress-testing agent named `CriticAgent` | Risk skills/agents but less aggressive veto gate |
| **Hard validation gates** | Explicit A+ to F grading with veto (min trades ≥ 100, MC survival ≥ 70%, WFE ≥ 0.5) | Metrics reported but no named grading |
| **Intent Parser** | Dedicated agent extracts targets from natural language | Skill-based, less structured |

### 7.3 Ideas Worth Adopting

If you want to incorporate Vibe-Trading ideas into StratForge AI:

1. **Skills-as-files pattern** — Move agent prompts from hardcoded Python into SKILL.md files. Makes the system more inspectable and community-extensible.

2. **5-layer context compression** — Especially the zero-cost **L2 context_collapse** (fold head+tail, drop middle) for long tool results. This is free latency win.

3. **Read/write tool batching** — Mark `compute_*` indicators as readonly → run in parallel via ThreadPoolExecutor. Big wins for multi-indicator strategies.

4. **AST validation for LLM code** — Before importing `signal_engine.py`, walk the AST and reject executable top-level statements. Low effort, high security payoff.

5. **Runtime fallback chains for data** — If primary data source fails, try alternates silently.

6. **Persistent memory with frozen snapshot** — Separate frozen-for-prompt-cache memory from per-query auto-recall retrieval.

7. **Swarm DAG YAML presets** — Let users author multi-agent workflows as YAML without touching Python. Much easier to share and iterate.

8. **Shadow Account concept** — If users can upload trade journals, extracting their own profitable pattern into a testable strategy would be unique to the Indian/global retail market StratForge targets.

9. **Multi-platform export (MT5 + TDX)** — Currently StratForge exports Pine Script v5. Adding MT5 (MQL5) and TradingView v6 would be competitive.

10. **Self-evolving skills** — Let the agent save learnings as new skills. StratForge has memory but not CRUD-able skill authoring.

---

## 8. File & Line Count Summary

Based on the repository study:

| Metric | Value |
|--------|-------|
| CLI entry point | `cli.py` — **2193 lines** |
| AgentLoop | `loop.py` — **789 lines** |
| Total Python files in `agent/src/` | ~200+ |
| Total skill docs | **74 SKILL.md + examples.md** |
| Test files | ~50 |
| Swarm presets | **29 YAML files** |
| Data loaders | 6 |
| Market engines | 7 + composite |
| Portfolio optimizers | 4 |
| LLM providers | 13 |

---

## 9. Dependencies Summary

### Python (from `pyproject.toml`)

**Core:** rich, pyyaml, langchain, langchain-core, langchain-openai, langgraph<0.3, langchain-checkpoint, python-dotenv, httpx, oauth-cli-kit

**Data/Compute:** pandas≥2.0, numpy, scipy, duckdb, scikit-learn, joblib

**Finance:** smartmoneyconcepts, pyharmonics (SMC + harmonic patterns)

**Data providers:** tushare, yfinance, akshare, ccxt, requests

**Documents:** openpyxl, python-docx, python-pptx, pypdfium2, Pillow

**Web server:** fastapi, uvicorn[standard], pydantic, python-multipart, sse-starlette

**MCP:** fastmcp

**Search:** ddgs (DuckDuckGo)

**Reports:** jinja2, matplotlib, weasyprint (PDF from HTML)

**CLI:** prompt_toolkit, rich

### JavaScript (from `frontend/package.json`)

**Core:** react 19, react-dom 19, typescript 5.7, vite 6

**State/Router:** zustand 5, react-router-dom 7

**UI:** tailwindcss 3, @tailwindcss/typography, clsx, tailwind-merge, lucide-react, sonner

**Data viz:** echarts 6

**Content:** react-markdown 9, remark-gfm 4, rehype-highlight 7

---

## 10. Final Assessment

**Vibe-Trading is an exceptionally mature, security-hardened, multi-market finance research agent.** It punches above its weight in:

- ✅ **Breadth of markets** — Truly global (China A + HK + US + crypto + futures + forex + options) with 6-source auto-fallback
- ✅ **Skill/swarm library depth** — 74 skills + 29 named multi-agent teams is a rare level of investment
- ✅ **Agent harness sophistication** — 5-layer compression, read/write batching, persistent memory, self-evolving skills
- ✅ **Security posture** — Explicit boundaries, AST validation, non-root containers, credential handling
- ✅ **Distribution flexibility** — PyPI package, Docker, MCP plugin, ClawHub all first-class

**Areas of concern:**
- ⚠️ **Web UI less polished than desktop apps** — Functional but not as slick as an Electron app
- ⚠️ **CLI is 2193 lines in one file** — Could use modularization
- ⚠️ **No explicit genetic algorithm for strategy evolution** — The agent "tries variants" but there's no named evolver
- ⚠️ **No hard pass/fail grading** — Metrics are reported but no A+/F classification with veto gates

**For StratForge AI development, Vibe-Trading is a goldmine of reusable ideas** — particularly the skills-as-MD-files pattern, 5-layer context compression, AST validation, and DAG swarm YAML presets. The Shadow Account feature is a genuinely novel product wedge worth studying.

---

*End of study. Last updated 2026-05-06.*
