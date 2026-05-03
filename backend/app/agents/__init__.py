"""Multi-agent system for autonomous strategy research.

Agents
------
- **MasterAgent** – Supervisor that orchestrates the full research loop.
- **DataAnalyst** – Direct indicator computation, no LLM needed.
- **StrategyArchitect** – LLM-powered strategy design from data profile.
- **Backtester** – Wraps ``run_full_pipeline`` for each variant.
- **Evaluator** – Deterministic veto check + improvement feedback.
"""

from .master import MasterAgent

__all__ = ["MasterAgent"]
