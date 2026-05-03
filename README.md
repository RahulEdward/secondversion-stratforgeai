# StratForge AI — Multi-Agent Trading Strategy Research Platform

> **Autonomous AI-powered backtesting engine** that designs, tests, optimizes, and validates trading strategies using a multi-agent architecture with a plugin-based skills system.

---

## 🚀 What It Does

StratForge AI is a desktop application where you simply describe what you want — *"Build me a profitable intraday strategy"* — and the AI autonomously:

1. **Analyzes your data** (regime detection, volatility profiling)
2. **Designs multiple strategy variants** (trend, mean-reversion, momentum)
3. **Backtests each variant** with realistic fees & slippage
4. **Optimizes parameters** via grid search
5. **Validates with Walk-Forward analysis** (overfitting detection)
6. **Runs Monte Carlo simulations** (statistical significance)
7. **Scores & grades** strategies (A+ to F with hard veto gates)
8. **Generates PDF reports** with equity curves and charts
9. **Iterates automatically** until a passing strategy is found

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                  Electron Desktop App            │
│                  (React + Vite UI)                │
├─────────────────────────────────────────────────┤
│               FastAPI Backend (Python)            │
│                                                   │
│  ┌─────────────┐  ┌──────────────────────────┐   │
│  │ Orchestrator │  │   Multi-Agent System      │   │
│  │ (Chat Loop)  │──│  ├─ MasterAgent          │   │
│  │              │  │  ├─ DataAnalyst           │   │
│  │              │  │  ├─ StrategyArchitect     │   │
│  │              │  │  ├─ Backtester            │   │
│  │              │  │  └─ Evaluator             │   │
│  └──────┬───────┘  └──────────────────────────┘   │
│         │                                         │
│  ┌──────▼──────────────────────────────────────┐  │
│  │        Skills Registry (Plugin System)       │  │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────────┐  │  │
│  │  │Indicators│ │Backtests │ │  Reporting   │  │  │
│  │  │ (65+)    │ │+Pipeline │ │  HTML+PDF    │  │  │
│  │  └──────────┘ └──────────┘ └─────────────┘  │  │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────────┐  │  │
│  │  │ Library  │ │ Dataset  │ │Agent Tools   │  │  │
│  │  │Save/Load │ │Validator │ │Shell/File/Py │  │  │
│  │  └──────────┘ └──────────┘ └─────────────┘  │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │         Core Engines                         │  │
│  │  VectorBT · Pandas · NumPy · Plotly · Jinja │  │
│  │  SQLite · Pydantic · Playwright (PDF)        │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## 🤖 Multi-Agent System

| Agent | LLM? | Speed | Role |
|-------|------|-------|------|
| **MasterAgent** | No | — | Orchestrates the full research loop |
| **DataAnalyst** | No | ~200ms | Computes indicators, classifies regime |
| **StrategyArchitect** | Yes | ~3s | Designs strategy variants from data profile |
| **Backtester** | No | ~5-15s | Runs full pipeline per variant |
| **Evaluator** | No | instant | Checks vetos, builds improvement feedback |

**Flow:** User Prompt → Master → Analyst → Architect → Backtester → Evaluator → (iterate if failing) → Report + Save

---

## 🔌 Skills System (Plugin Architecture)

```
backend/app/skills/
├── base.py                  # BaseSkill ABC (strict contract)
├── registry.py              # Auto-discovery + routing + timeout
├── indicator_skill/         # 65+ technical indicators
├── backtest_skill/          # Backtest + optimize + WF + MC + scoring
├── report_skill/            # HTML+PDF report generation
├── library_skill/           # Strategy save/load/list
├── dataset_skill/           # Dataset inspection & validation
└── agent_skill/             # Shell/file/Python system tools
```

**Adding a new skill = just drop a folder.** No core code changes required.

Each skill implements:
```python
class Skill(BaseSkill):
    name = "my_skill"
    description = "What it does"
    
    def tools(self):       # Returns LLM tool schemas
    async def execute():   # Runs the logic
```

---

## 📊 Scoring System

Strategies are graded **A+ to F** with hard veto gates:

| Veto Rule | Threshold |
|-----------|-----------|
| Minimum trades | ≥ 100 |
| Max drawdown | > -50% |
| Profit factor | > 1.0 |
| Walk-forward efficiency | ≥ 0.5 |
| Monte Carlo survival | ≥ 70% |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Desktop | Electron 33 |
| Frontend | React 18 + Vite |
| Backend | FastAPI + Uvicorn |
| Backtesting | VectorBT Pro |
| Data | Pandas + NumPy + Parquet |
| Charts | Plotly.js |
| Reports | Jinja2 + Playwright (PDF) |
| Database | SQLite |
| AI Providers | Anthropic / OpenAI / Google |

---

## 📦 Setup

### Prerequisites
- **Node.js** 18+
- **Python** 3.11+
- **Git**

### Install

```bash
# Clone
git clone https://github.com/RahulEdward/secondversion-stratforgeai.git
cd secondversion-stratforgeai

# Frontend dependencies
npm install

# Backend dependencies
cd backend
pip install -r requirements.txt
cd ..
```

### Run

```bash
npm run dev
```

This starts both:
- **UI:** http://localhost:5173 (Electron window)
- **API:** http://127.0.0.1:8765

---

## 🧪 Quick Test

Open a new session in the app and type:

```
Build me a profitable trading strategy on this data
```

The AI will autonomously research, test, iterate, and deliver the best strategy with a full report.

---

## 📁 Project Structure

```
startfoge-ai-main/
├── backend/
│   ├── app/
│   │   ├── agents/           # Multi-agent system
│   │   │   ├── master.py     # Supervisor agent
│   │   │   ├── analyst.py    # Data analysis
│   │   │   ├── architect.py  # Strategy design
│   │   │   ├── backtester.py # Pipeline execution
│   │   │   └── evaluator.py  # Result evaluation
│   │   ├── skills/           # Plugin system
│   │   │   ├── registry.py   # Auto-discovery
│   │   │   ├── base.py       # Skill interface
│   │   │   └── *_skill/      # Individual skills
│   │   ├── indicators/       # 65+ indicator implementations
│   │   ├── reports/          # Report templates + renderer
│   │   ├── orchestrator.py   # Chat loop + agent routing
│   │   ├── strategies.py     # Strategy DSL (Pydantic)
│   │   ├── backtest.py       # VectorBT engine
│   │   ├── optimize.py       # Grid optimization
│   │   ├── validate.py       # Walk-forward + Monte Carlo
│   │   ├── scoring.py        # A+ to F grading
│   │   ├── tools.py          # Tool schemas
│   │   └── tool_exec.py      # Tool dispatcher
│   └── main.py               # FastAPI entry point
├── src/                      # React frontend
├── electron/                 # Electron main process
└── package.json
```

---

## 📄 License

MIT

---

**Built with ❤️ by RahulEdward**
