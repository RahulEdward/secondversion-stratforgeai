import React, { useState } from 'react';
import { X, BookOpen, Terminal, LineChart, ShieldCheck, Zap, Download, Maximize2, Minimize2, BrainCircuit, Activity, Network } from 'lucide-react';
import { cn } from '@/lib/cn';
import Tooltip from '../ui/Tooltip';

interface Props {
  open: boolean;
  onClose: () => void;
}

const SECTIONS = [
  {
    id: 'intro',
    title: 'Introduction',
    icon: BookOpen,
    content: (
      <div className="space-y-6">
        <div>
          <h3 className="text-xl font-bold text-fg tracking-tight">What is StratForge AI?</h3>
          <p className="text-sm text-fg-subtle leading-relaxed mt-2">
            StratForge AI bridges the gap between retail trading tools (like TradingView) and institutional quantitative research platforms. It is a fully automated, agentic AI research engine designed to transform abstract trading ideas into statistically validated, production-ready algorithms.
          </p>
        </div>
        
        <div>
          <h4 className="text-sm font-semibold text-fg">Core Capabilities</h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-3">
            <Tooltip content="The AI automatically runs multiple iterations, mutating parameters to find the best possible setup without human intervention.">
              <div className="bg-bg-sidebar border border-border-subtle p-3 rounded-lg flex items-center gap-2 hover:border-accent/50 transition-colors cursor-help">
                <BrainCircuit size={16} className="text-accent shrink-0" />
                <span className="text-xs font-medium text-fg">8-Agent Loop</span>
              </div>
            </Tooltip>

            <Tooltip content="Walk-Forward Efficiency tests the strategy on unseen Out-Of-Sample data to mathematically prove it's not overfit.">
              <div className="bg-bg-sidebar border border-border-subtle p-3 rounded-lg flex items-center gap-2 hover:border-accent/50 transition-colors cursor-help">
                <ShieldCheck size={16} className="text-emerald-400 shrink-0" />
                <span className="text-xs font-medium text-fg">WFE Testing</span>
              </div>
            </Tooltip>

            <Tooltip content="Reshuffles trades 1,000+ times to simulate alternative market realities, ensuring the strategy doesn't carry hidden risks of ruin.">
              <div className="bg-bg-sidebar border border-border-subtle p-3 rounded-lg flex items-center gap-2 hover:border-accent/50 transition-colors cursor-help">
                <Activity size={16} className="text-amber-400 shrink-0" />
                <span className="text-xs font-medium text-fg">Monte Carlo</span>
              </div>
            </Tooltip>

            <Tooltip content="Genetic algorithms swap entry/exit logic and mutate constraints to evolve weak strategies into highly profitable ones over time.">
              <div className="bg-bg-sidebar border border-border-subtle p-3 rounded-lg flex items-center gap-2 hover:border-accent/50 transition-colors cursor-help">
                <Network size={16} className="text-purple-400 shrink-0" />
                <span className="text-xs font-medium text-fg">Strategy Evolver</span>
              </div>
            </Tooltip>

            <Tooltip content="Generates native TradingView Pine Script v5 code from your validated strategy, complete with inputs and visual drawings.">
              <div className="bg-bg-sidebar border border-border-subtle p-3 rounded-lg flex items-center gap-2 hover:border-accent/50 transition-colors cursor-help">
                <Terminal size={16} className="text-blue-400 shrink-0" />
                <span className="text-xs font-medium text-fg">Pine Script Export</span>
              </div>
            </Tooltip>
            
            <Tooltip content="Produces a copy-paste ready Markdown signal message with detailed metrics and R:R ratios for Discord/Telegram groups.">
              <div className="bg-bg-sidebar border border-border-subtle p-3 rounded-lg flex items-center gap-2 hover:border-accent/50 transition-colors cursor-help">
                <Download size={16} className="text-green-400 shrink-0" />
                <span className="text-xs font-medium text-fg">Signal Generation</span>
              </div>
            </Tooltip>
          </div>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-fg">The Value for Traders</h4>
          <p className="text-sm text-fg-subtle leading-relaxed mt-1">
            Manual backtesting is prone to psychological biases, and standard AI code generators often produce "overfit" strategies that look amazing on historical data but collapse in live markets. StratForge solves this by employing an autonomous loop that not only writes the code but rigorously validates it against institutional stress-tests.
          </p>
        </div>
      </div>
    )
  },
  {
    id: 'basics',
    title: 'Core Workflow',
    icon: Terminal,
    content: (
      <div className="space-y-5">
        <h3 className="text-xl font-bold text-fg tracking-tight">Basic Operations</h3>
        
        <div className="space-y-2">
          <h4 className="text-base font-semibold text-fg text-accent">1. Data Management (OHLCV)</h4>
          <p className="text-sm text-fg-subtle leading-relaxed">
            Every strategy is anchored to real data. Upload your historical data in CSV or Parquet format via the sidebar. The system requires Open, High, Low, Close, and Volume columns. Once selected, StratForge runs a baseline analysis to detect the market regime (Trending, Ranging, Volatile) using ADX, ATR, and EMA slopes.
          </p>
        </div>

        <div className="space-y-2">
          <h4 className="text-base font-semibold text-fg text-accent">2. Natural Language Intent Parsing</h4>
          <p className="text-sm text-fg-subtle leading-relaxed">
            You do not need to specify exact parameters. Our NLP <strong>Intent Parser</strong> breaks down conversational language into a strict JSON schema. It extracts:
          </p>
          <ul className="list-disc pl-5 space-y-1 text-sm text-fg-subtle">
            <li><strong>Market & Timeframe:</strong> (e.g., Nifty 5m, XAUUSD 1H)</li>
            <li><strong>Style:</strong> (e.g., Scalping, Swing, Mean-Reversion)</li>
            <li><strong>Risk Tolerance:</strong> (Aggressive, Moderate, Conservative)</li>
          </ul>
          <div className="bg-bg-sidebar p-3 rounded-md border border-border-subtle text-xs font-mono text-fg-muted mt-2">
            Example: "Find a safe trend-following setup for Crypto on 15m charts. Keep drawdowns under 10%."
          </div>
        </div>

        <div className="space-y-2">
          <h4 className="text-base font-semibold text-fg text-accent">3. Pre-built Templates</h4>
          <p className="text-sm text-fg-subtle leading-relaxed">
            The Templates Library (accessible under "More") offers pre-engineered prompts for industry-standard strategies (VWAP Breakouts, Dual SuperTrend, Bollinger Squeeze). These act as excellent starting seeds for the Evolutionary Engine.
          </p>
        </div>
      </div>
    )
  },
  {
    id: 'advanced',
    title: 'The AI Research Loop',
    icon: Zap,
    content: (
      <div className="space-y-5">
        <div>
          <h3 className="text-xl font-bold text-fg tracking-tight">The 8-Stage Autonomous Pipeline</h3>
          <p className="text-sm text-fg-subtle mt-2 leading-relaxed">
            When a research request is initiated, StratForge spins up multiple specialized AI agents working in concert.
          </p>
        </div>
        
        <div className="space-y-4">
          <div className="pl-4 border-l-2 border-accent/40 relative">
            <div className="absolute w-2 h-2 bg-accent rounded-full -left-[5px] top-1.5" />
            <h4 className="text-sm font-bold text-fg">1. Analyst & Planner Agents</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              Analyzes the dataset to determine market regime. The Planner then maps your intent to specific strategy families (e.g., assigning Momentum and Breakout templates if the market is trending).
            </p>
          </div>
          
          <div className="pl-4 border-l-2 border-accent/40 relative">
            <div className="absolute w-2 h-2 bg-accent rounded-full -left-[5px] top-1.5" />
            <h4 className="text-sm font-bold text-fg">2. Architect Agent</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              Generates 6-10 unique, structurally distinct strategy variants. It combines different indicators (RSI, MACD, Donchian, Ichimoku) ensuring logical non-redundancy.
            </p>
          </div>

          <div className="pl-4 border-l-2 border-accent/40 relative">
            <div className="absolute w-2 h-2 bg-accent rounded-full -left-[5px] top-1.5" />
            <h4 className="text-sm font-bold text-fg">3. Backtesting Engine</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              Vectorized backtester runs all variants through historical data, computing Sharpe, Sortino, Profit Factor, and Drawdowns, factoring in realistic fees and slippage.
            </p>
          </div>

          <div className="pl-4 border-l-2 border-accent/40 relative">
            <div className="absolute w-2 h-2 bg-accent rounded-full -left-[5px] top-1.5" />
            <h4 className="text-sm font-bold text-fg">4. Critic Agent</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              The harshest judge. It calculates overfitting scores, checks for structural instability, and mandates strict risk controls (Stop-Losses and Take-Profits). It assigns a final Grade (A+ to F) and issues "Vetos" against failing logic.
            </p>
          </div>

          <div className="pl-4 border-l-2 border-transparent relative">
            <div className="absolute w-2 h-2 bg-accent rounded-full -left-[5px] top-1.5" />
            <h4 className="text-sm font-bold text-fg">5. Evolutionary Engine</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              If strategies fail, the Evolver takes the best traits (Elitism), swaps entry/exit logic between variants (Crossover), and alters parameters by a random walk (Mutation) to try again. The loop repeats up to 5 times.
            </p>
          </div>
        </div>
      </div>
    )
  },
  {
    id: 'validation',
    title: 'Validation Metrics',
    icon: ShieldCheck,
    content: (
      <div className="space-y-5">
        <div>
          <h3 className="text-xl font-bold text-fg tracking-tight">Institutional Stress-Testing</h3>
          <p className="text-sm text-fg-subtle mt-2 leading-relaxed">
            A beautiful equity curve on past data is meaningless if the strategy is curve-fit. StratForge employs two major stress tests to guarantee robustness.
          </p>
        </div>
        
        <div className="grid gap-4 mt-4">
          <div className="bg-bg-sidebar p-4 rounded-lg border border-border-subtle shadow-sm">
            <h4 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
              <LineChart size={16} /> Walk-Forward Efficiency (WFE)
            </h4>
            <p className="text-xs text-fg-subtle mt-2 leading-relaxed">
              StratForge divides your data into 'In-Sample' (IS) blocks for training, and 'Out-of-Sample' (OOS) blocks for blind testing. It simulates how the strategy performs on data it has never seen.
            </p>
            <div className="mt-3 bg-bg-panel/50 p-2 rounded border border-border-subtle/50 text-[11px] text-fg-muted font-mono">
              Formula: WFE = (Annualized OOS Return) / (Annualized IS Return)<br/>
              Threshold: WFE &lt; 0.5 triggers an automatic rejection by the Critic.
            </div>
          </div>
          
          <div className="bg-bg-sidebar p-4 rounded-lg border border-border-subtle shadow-sm">
            <h4 className="text-sm font-bold text-amber-400 flex items-center gap-2">
              <Zap size={16} /> Monte Carlo Survival Rate
            </h4>
            <p className="text-xs text-fg-subtle mt-2 leading-relaxed">
              What if the exact same trades happened in the worst possible order? Monte Carlo Bootstrapping reshuffles the strategy's trades 1,000+ times to simulate alternative realities.
            </p>
            <p className="text-xs text-fg-subtle mt-2 leading-relaxed">
              It calculates the <strong>Risk of Ruin</strong> and max drawdown distributions. If the strategy has a high probability of exceeding your maximum acceptable drawdown in these simulations, it is marked as unstable.
            </p>
          </div>
        </div>
      </div>
    )
  },
  {
    id: 'export',
    title: 'Export & Deployment',
    icon: Download,
    content: (
      <div className="space-y-5">
        <div>
          <h3 className="text-xl font-bold text-fg tracking-tight">Deployment Ready</h3>
          <p className="text-sm text-fg-subtle mt-2 leading-relaxed">
            Finding a strategy is only half the battle. StratForge provides built-in tools to take your validated edge straight to production.
          </p>
        </div>
        
        <div className="space-y-4">
          <div className="border-l-2 border-emerald-500/50 pl-4">
            <h4 className="text-sm font-bold text-fg">TradingView Pine Script v5 Export</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              With a single click, StratForge compiles its internal logic into native TradingView Pine Script v5. 
            </p>
            <ul className="list-disc pl-5 mt-2 space-y-1 text-xs text-fg-subtle">
              <li>Automatically declares all required indicators (e.g., `ta.sma`, `ta.rsi`).</li>
              <li>Generates precise `strategy.entry` and `strategy.close` blocks.</li>
              <li>Implements advanced risk management: ATR-based stop losses, trailing stops, and fixed percentage take-profits seamlessly.</li>
            </ul>
          </div>

          <div className="border-l-2 border-blue-500/50 pl-4 mt-6">
            <h4 className="text-sm font-bold text-fg">Signal Generation</h4>
            <p className="text-xs text-fg-subtle mt-1 leading-relaxed">
              If you run a trading community or prefer manual execution, the platform can format the strategy into a clean, markdown-based Signal Message.
            </p>
            <ul className="list-disc pl-5 mt-2 space-y-1 text-xs text-fg-subtle">
              <li>Includes clear Entry, Stop Loss, and Take Profit levels.</li>
              <li>Embeds the strategy's Grade, Sharpe Ratio, and Win Rate to build trust.</li>
              <li>Ready to be copy-pasted into Telegram, Discord, or Twitter.</li>
            </ul>
          </div>
        </div>
      </div>
    )
  }
];

export default function DocumentationModal({ open, onClose }: Props) {
  const [activeTab, setActiveTab] = useState(SECTIONS[0].id);
  const [isMaximized, setIsMaximized] = useState(false);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div 
        className={cn(
          "bg-bg-panel border border-border shadow-2xl flex overflow-hidden animate-in fade-in zoom-in-95 duration-200 transition-all",
          isMaximized ? "w-screen h-screen rounded-none" : "w-[900px] h-[650px] rounded-xl"
        )}
      >
        
        {/* Sidebar */}
        <div className="w-64 bg-bg-sidebar border-r border-border-subtle flex flex-col shrink-0">
          <div className="p-5 border-b border-border-subtle bg-bg-titlebar">
            <div className="flex items-center gap-2 text-fg">
              <BookOpen size={18} className="text-accent" />
              <h2 className="font-semibold tracking-tight text-base">Pro Documentation</h2>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto py-4 px-3 space-y-1.5">
            {SECTIONS.map((sec) => {
              const Icon = sec.icon;
              const isActive = activeTab === sec.id;
              return (
                <button
                  key={sec.id}
                  onClick={() => setActiveTab(sec.id)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-3 rounded-lg text-sm transition-all duration-200 text-left",
                    isActive 
                      ? "bg-accent/15 text-accent font-medium shadow-sm border border-accent/20" 
                      : "text-fg-subtle border border-transparent hover:bg-bg-panel hover:text-fg hover:border-border-subtle"
                  )}
                >
                  <Icon size={16} className={isActive ? "text-accent" : "text-fg-muted"} />
                  {sec.title}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 flex flex-col relative bg-bg-panel">
          <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
            <button 
              onClick={() => setIsMaximized(!isMaximized)} 
              className="text-fg-muted hover:text-fg transition-colors bg-bg-panel/80 rounded-full p-1.5 hover:bg-bg-sidebar"
              title={isMaximized ? "Restore down" : "Maximize"}
            >
              {isMaximized ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>
            <button 
              onClick={onClose} 
              className="text-fg-muted hover:text-fg transition-colors bg-bg-panel/80 rounded-full p-1.5 hover:bg-bg-sidebar"
              title="Close"
            >
              <X size={20} />
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto p-10 custom-scrollbar">
            {SECTIONS.map((sec) => (
              <div 
                key={sec.id} 
                className={cn(
                  "transition-all duration-300 transform max-w-4xl",
                  activeTab === sec.id ? "opacity-100 translate-y-0 block" : "opacity-0 translate-y-4 hidden"
                )}
              >
                {sec.content}
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
