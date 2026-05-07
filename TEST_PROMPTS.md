# 🧪 StratForge AI - Test Prompts

A curated list of prompts to test and explore all features of StratForge AI, from basic strategy generation to advanced multi-agent validation.

---

## 🎯 Basic Strategy Prompts

### 1. Simple strategy build
```
Build a profitable intraday momentum strategy for XAUUSD on 5-minute charts. Keep max drawdown below 15%.
```

### 2. Specific indicator-based
```
Create a swing trading strategy for EURUSD 1H using RSI and MACD. Target 1.5+ Sharpe ratio and at least 200 trades.
```

### 3. Trend-following
```
Design a trend-following system for BTCUSD daily charts using SuperTrend and moving averages. Risk 1% per trade.
```

---

## 🧪 Advanced Testing Prompts

### 4. Multi-indicator complex
```
Build an aggressive scalping strategy for NIFTY 1-minute charts combining VWAP, Bollinger Bands, and Stochastic. Profit factor must exceed 1.5.
```

### 5. Mean reversion
```
Create a mean-reversion strategy for SPY 15m using Keltner Channels and RSI divergence. Minimum 300 trades with 60% win rate.
```

### 6. Breakout strategy
```
Design a Dual SuperTrend breakout strategy for GOLD 30-minute charts with proper R:R of 1:2 minimum.
```

---

## 📊 Feature-Specific Tests

### 7. Test the Critic Agent
```
Build a strategy that gets A+ grade. It must pass walk-forward efficiency above 0.7 and Monte Carlo survival above 80%.
```

### 8. Test Evolution (Genetic Algorithm)
```
Evolve an Ichimoku Cloud strategy for USDJPY 4H over 5 generations. Optimize for maximum Sharpe ratio.
```

### 9. Test Pine Script export
```
Create a MACD crossover strategy for TradingView. After backtesting, export it as Pine Script v5.
```

### 10. Test Telegram signals
```
Build a simple EMA crossover strategy for ETHUSD 1H and generate a Telegram signal template for live alerts.
```

---

## 🔥 Stress Test Prompts

### 11. Tough validation
```
I want an institutional-grade strategy for XAUUSD 15m. Requirements: Sharpe > 2.0, max DD < 10%, min 500 trades, WFE > 0.6.
```

### 12. Regime-aware
```
Analyze the current market regime for BTCUSD daily and build a strategy that works in both trending and ranging conditions.
```

### 13. Multi-timeframe
```
Design a strategy that uses 1H for entry signals and 4H for trend confirmation on EURUSD.
```

---

## 💡 Quick Starter (Recommended First Test)

Start with this one — it exercises the full 8-agent pipeline cleanly:

```
Build a profitable trading strategy for XAUUSD on 15-minute charts. Use momentum indicators, keep drawdown under 20%, and show me the walk-forward results with Monte Carlo validation.
```

---

## 📝 What to Check While Testing

- ✅ **Stepper progress** at top showing 8 agents running (IntentParser → Planner → Architect → Critic → Evolver → Backtester → Analyst → MasterAgent)
- ✅ **Artifacts panel** opening with reports
- ✅ **Live streaming** messages in chat
- ✅ **Strategy grade** (A+ to F)
- ✅ **Metrics** — Sharpe Ratio, Profit Factor, Walk-Forward Efficiency (WFE), Monte Carlo Survival Rate
- ✅ **Export buttons** for Pine Script v5 and Telegram/Discord signals
- ✅ **Genetic evolution** iterations (mutation, crossover)
- ✅ **PDF/HTML reports** generation

---

## ⚙️ Pre-Testing Setup

Before running these prompts, make sure:

1. **Upload a dataset** — Go to sidebar and upload an OHLCV CSV/Excel file (or use existing datasets)
2. **Configure AI Provider** — Open Settings → Providers and add API key for one of:
   - Anthropic (Claude)
   - OpenAI (GPT-4)
   - Google (Gemini)
   - Ollama (local models — no key needed)
3. **Select a project** — Create or select a project from the sidebar
4. **Create a session** — Click "New Session" to start a fresh chat

---

## 🎓 Validation Gates Reference

Strategies are graded A+ to F with these hard veto gates:

| Metric | Minimum |
|--------|---------|
| Minimum trades | ≥ 100 |
| Max drawdown | > -50% |
| Profit factor | > 1.0 |
| Walk-forward efficiency (WFE) | ≥ 0.5 |
| Monte Carlo survival | ≥ 70% |

---

## 🤖 The 8-Agent Architecture

| # | Agent | Role |
|---|-------|------|
| 1 | **IntentParser** | Parses natural language into JSON schema |
| 2 | **DataAnalyst** | Computes baseline indicators, classifies regime |
| 3 | **PlannerAgent** | Selects logic families and topology |
| 4 | **StrategyArchitect** | Builds 6-10 structurally diverse variants |
| 5 | **Backtester** | Vectorized grid search + historical simulation |
| 6 | **CriticAgent** | Aggressive stress-testing and vetoing |
| 7 | **StrategyEvolver** | Genetic algorithms (crossover, mutation, elitism) |
| 8 | **MasterAgent** | Orchestrates the lifecycle |

---

*Happy testing! 🚀*
