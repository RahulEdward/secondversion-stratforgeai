# 📋 StratForge AI — Trader Task List

A complete list of what a trader can do in StratForge AI, organized by skill level. Each task includes a ready-to-use example prompt with real market symbols.

---

## 🟢 BASIC TASKS (Beginner Trader)

Tasks that require minimal trading knowledge. Upload data, ask questions, get results.

---

### 1. Upload Market Data
Upload a CSV/XLSX file with OHLCV data for any instrument.

**Example:**
```
Upload XAUUSD_5m.csv from your computer via the sidebar dataset panel.
```

---

### 2. Simple Strategy Backtest
Ask the AI to build and test a basic strategy on your data.

**Example (Forex - Gold):**
```
Backtest a simple EMA crossover strategy on my XAUUSD 5-minute data. Use EMA 9 and EMA 21. Show me the results.
```

**Example (Crypto - Bitcoin):**
```
Test a basic RSI strategy on BTC-USDT daily data. Buy when RSI drops below 30, sell when it goes above 70.
```

**Example (US Stock - Apple):**
```
Backtest a moving average crossover on AAPL.US daily data. Use 20-day and 50-day SMA.
```

**Example (Indian Index - Nifty):**
```
Run a simple MACD crossover strategy on NIFTY 15-minute data and show me win rate and profit factor.
```

---

### 3. View Strategy Metrics
Ask for performance numbers after a backtest.

**Example:**
```
Show me the Sharpe ratio, max drawdown, total return, and number of trades for the last strategy.
```

---

### 4. Compare Two Strategies
Run two different approaches and compare.

**Example (Forex - EUR/USD):**
```
Compare RSI mean-reversion vs EMA trend-following on my EURUSD 1H data. Which one has better Sharpe?
```

---

### 5. Explain a Strategy Concept
Ask the AI to teach you something.

**Example:**
```
Explain what walk-forward efficiency means and why it matters for my strategy.
```

---

### 6. Get Market Regime Analysis
Understand if the market is trending or ranging.

**Example (Crypto - Ethereum):**
```
Analyze my ETH-USDT 4H data. Is it trending or ranging? What indicators confirm this?
```

---

### 7. Generate a Report
Get a visual HTML/PDF report of backtest results.

**Example:**
```
Generate a full report for my last backtest with equity curve, drawdown chart, and trade list.
```

---

## 🟡 INTERMEDIATE TASKS (Active Trader)

Tasks that require some trading experience. Strategy design, optimization, validation.

---

### 8. Multi-Indicator Strategy
Combine multiple indicators for entry/exit.

**Example (Forex - GBP/USD):**
```
Build a strategy for GBPUSD 15m using Bollinger Bands + RSI + ADX filter. Enter long when price touches lower band, RSI < 35, and ADX > 20. Exit at middle band or RSI > 65.
```

**Example (Crypto - Solana):**
```
Create a momentum strategy for SOL-USDT 1H combining SuperTrend, MACD histogram, and volume spike detection. Target 2:1 reward-to-risk.
```

**Example (US Stock - Tesla):**
```
Design a breakout strategy for TSLA.US daily using Donchian Channel (20-period) with ATR-based stops and ADX trend filter above 25.
```

---

### 9. Strategy Optimization
Sweep parameters to find the best settings.

**Example (Forex - USD/JPY):**
```
Optimize my RSI strategy on USDJPY 1H data. Sweep RSI period from 7 to 21, overbought from 65 to 80, oversold from 20 to 35. Find the best combination by Sharpe ratio.
```

**Example (Indian Stock - Reliance):**
```
Optimize EMA crossover on RELIANCE 15m data. Test fast EMA 5-15 and slow EMA 20-50. Maximize profit factor.
```

---

### 10. Walk-Forward Validation
Test if the strategy works out-of-sample.

**Example (Crypto - Bitcoin):**
```
Run walk-forward analysis on my BTC-USDT MACD strategy with 4 folds. Show me the walk-forward efficiency score.
```

---

### 11. Monte Carlo Simulation
Stress-test the strategy with randomized trade sequences.

**Example (Forex - Gold):**
```
Run 1000 Monte Carlo simulations on my XAUUSD strategy. What's the survival rate? What's the worst-case drawdown at 95th percentile?
```

---

### 12. Risk Management Design
Add proper stops and position sizing.

**Example (US Stock - NVIDIA):**
```
Add ATR-based stop loss (2x ATR), trailing stop (1.5x ATR), and take profit (3x ATR) to my NVDA.US momentum strategy. Risk 1% per trade.
```

---

### 13. Multi-Timeframe Strategy
Use higher timeframe for direction, lower for entry.

**Example (Forex - EUR/USD):**
```
Build a multi-timeframe strategy for EURUSD: use 4H EMA(50) for trend direction, enter on 15m RSI pullbacks in the trend direction. Exit on 15m RSI reversal.
```

---

### 14. Sector/Market Comparison
Test same strategy across different instruments.

**Example:**
```
Test my Bollinger Band mean-reversion strategy on XAUUSD, EURUSD, GBPUSD, and USDJPY 1H data. Which pair gives the best results?
```

---

### 15. Export to TradingView
Get Pine Script code for your strategy.

**Example:**
```
Export my winning XAUUSD SuperTrend strategy as TradingView Pine Script v5 so I can use it on my charts.
```

---

### 16. Pattern Recognition
Detect chart patterns in your data.

**Example (Crypto - Bitcoin):**
```
Scan my BTC-USDT daily data for head-and-shoulders, double tops, and triangle patterns. List the dates where they occurred.
```

---

### 17. Factor Analysis
Test if a factor predicts returns.

**Example (US Stocks):**
```
Run factor analysis on SPY, AAPL.US, MSFT.US, GOOGL.US, AMZN.US, NVDA.US using momentum factor (20-day return) over the last 2 years. Show IC and IR.
```

---

### 18. Volatility Analysis
Understand volatility regimes.

**Example (Forex - Gold):**
```
Analyze volatility regimes in my XAUUSD data using ATR percentile bands. Identify high-vol and low-vol periods. Which regime is better for my breakout strategy?
```

---

## 🔴 ADVANCED TASKS (Professional Trader)

Tasks for experienced quants. Multi-agent research, portfolio optimization, swarm intelligence.

---

### 19. Full Autonomous Research Pipeline
Let the AI design, test, optimize, validate, and grade strategies automatically.

**Example (Forex - Gold):**
```
Build me a profitable intraday strategy for XAUUSD 5m. Requirements: Sharpe > 1.5, max drawdown < 15%, at least 200 trades, walk-forward efficiency > 0.6, Monte Carlo survival > 80%. Iterate until you find something that passes.
```

**Example (Crypto - Ethereum):**
```
Research an aggressive momentum strategy for ETH-USDT 15m. I want Sharpe above 2.0, profit factor above 1.5, and at least 500 trades. Use genetic evolution to optimize.
```

**Example (US Stock - S&P 500):**
```
Find a swing trading strategy for SPY daily that works in both trending and ranging markets. Must pass walk-forward with WFE > 0.5 and Monte Carlo survival > 75%.
```

---

### 20. Multi-Agent Swarm Research
Deploy a team of specialized AI agents for deep analysis.

**Example (Investment Committee):**
```
Run an investment committee swarm on XAUUSD. I want a bull analyst, bear analyst, risk officer, and portfolio manager to debate whether gold is a buy at current levels.
```

**Example (Quant Strategy Desk):**
```
Deploy the quant strategy desk swarm to screen, research, backtest, and risk-audit a momentum strategy for BTC-USDT over the last year.
```

**Example (Technical Analysis Panel):**
```
Run the technical analysis panel swarm on EURUSD 4H. I want classic TA, Ichimoku, harmonic patterns, Elliott Wave, and Smart Money Concepts analysts to give their consensus view.
```

---

### 21. Cross-Market Portfolio Strategy
Build a strategy that trades multiple markets simultaneously.

**Example:**
```
Design a cross-market portfolio strategy trading XAUUSD, BTC-USDT, EURUSD, and SPY simultaneously. Use risk parity allocation. Backtest with shared capital pool of $100,000.
```

---

### 22. Shadow Account Analysis
Extract your own trading rules from a broker journal.

**Example:**
```
Analyze my trade journal (uploaded CSV). Extract my profitable patterns as 3-5 rules. Then backtest those rules across forex and crypto markets. Show me how much money I'm leaving on the table by not following my own rules consistently.
```

---

### 23. Options Pricing & Greeks
Calculate option values and sensitivities.

**Example:**
```
Price a XAUUSD call option: spot $2400, strike $2450, 30 days to expiry, volatility 18%, risk-free rate 4.5%. Show me Delta, Gamma, Theta, Vega.
```

---

### 24. Regime-Adaptive Strategy
Build a strategy that switches behavior based on market conditions.

**Example (Forex - Gold):**
```
Build a regime-adaptive strategy for XAUUSD 1H: use trend-following (EMA crossover) when ADX > 25, switch to mean-reversion (Bollinger Bands) when ADX < 20. Include proper transition logic.
```

---

### 25. Statistical Arbitrage / Pair Trading
Find correlated pairs and trade the spread.

**Example:**
```
Analyze correlation between XAUUSD and EURUSD over the last year. If they're correlated, design a pair trading strategy that profits from spread divergence.
```

---

### 26. Machine Learning Strategy
Use ML models for signal generation.

**Example (Crypto - Bitcoin):**
```
Build an ML-based strategy for BTC-USDT daily using Random Forest. Features: RSI(14), MACD histogram, Bollinger %B, ATR percentile, volume ratio. Train on 2022-2024, test on 2025.
```

---

### 27. Strategy Evolution (Genetic Algorithm)
Evolve strategies through mutation and crossover.

**Example (Forex - EUR/USD):**
```
Start with 10 random strategy variants for EURUSD 1H. Evolve them over 5 generations using genetic algorithm (crossover + mutation). Keep the top 3 by Sharpe ratio. Show me the evolution progress.
```

---

### 28. Institutional-Grade Validation
Full stress testing with all validation methods.

**Example (Forex - Gold):**
```
Run institutional-grade validation on my XAUUSD strategy:
- Walk-forward analysis (5 folds)
- Monte Carlo simulation (2000 iterations)
- Bootstrap confidence intervals (95%)
- Benchmark comparison vs buy-and-hold
- Overfitting detection
Grade it A+ to F.
```

---

### 29. Custom Indicator Development
Create and test custom indicators.

**Example:**
```
Create a custom indicator that combines RSI divergence with volume profile. When price makes a new low but RSI doesn't, AND volume is below 20-bar average, generate a buy signal. Backtest it on XAUUSD 15m.
```

---

### 30. Portfolio Optimization
Optimize allocation across multiple assets.

**Example:**
```
I have positions in XAUUSD, BTC-USDT, EURUSD, SPY, and AAPL.US. Run mean-variance optimization to find the optimal allocation. Then compare with risk parity and equal volatility approaches. Show the efficient frontier.
```

---

### 31. Sentiment & News Analysis
Analyze market sentiment from web sources.

**Example:**
```
Search the web for current gold (XAUUSD) sentiment. Check analyst forecasts, COT positioning, and recent news. Summarize bullish vs bearish factors.
```

---

### 32. Strategy Deployment Preparation
Get your strategy ready for live trading.

**Example:**
```
My XAUUSD EMA crossover strategy passed all tests (Grade A-). Now:
1. Export it as Pine Script v5 for TradingView alerts
2. Generate a Telegram signal template
3. Write a risk management checklist for live deployment
4. Calculate the minimum account size needed for 1% risk per trade
```

---

## 📊 Market Symbols Reference

| Market | Symbols Used in Examples |
|--------|--------------------------|
| **Forex** | XAUUSD, EURUSD, GBPUSD, USDJPY |
| **Crypto** | BTC-USDT, ETH-USDT, SOL-USDT |
| **US Stocks** | AAPL.US, TSLA.US, NVDA.US, MSFT.US, GOOGL.US, AMZN.US, SPY |
| **Indian** | NIFTY, RELIANCE |
| **Timeframes** | 1m, 5m, 15m, 30m, 1H, 4H, Daily |

---

## ⚡ Quick Start Recommendations

| Your Level | Start With | Task # |
|------------|-----------|--------|
| **Never traded** | Upload data + simple backtest | #1, #2, #3 |
| **Know basics** | Multi-indicator + optimization | #8, #9, #11 |
| **Active trader** | Full pipeline + validation | #19, #20, #28 |
| **Quant/Pro** | Swarm + ML + portfolio | #20, #21, #26, #30 |

---

## 🎯 Best First Prompt (Copy-Paste Ready)

```
Build a profitable intraday momentum strategy for XAUUSD on 5-minute charts. Use RSI and EMA indicators. Keep max drawdown below 15% and target at least 200 trades. Show me walk-forward and Monte Carlo results.
```

---

*StratForge AI — Design, Test, Optimize, Validate. Zero code required.*
