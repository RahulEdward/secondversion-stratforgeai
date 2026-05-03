"""Multi-agent system for autonomous strategy research.

Agents
------
- **MasterAgent** – Supervisor that orchestrates the full research loop.
- **IntentParser** – Extracts structured parameters from vague user requests.
- **PlannerAgent** – Decomposes intent into a structured research plan.
- **DataAnalyst** – Direct indicator computation, no LLM needed.
- **StrategyArchitect** – LLM-powered strategy design from data profile.
- **Backtester** – Wraps ``run_full_pipeline`` for each variant.
- **Evaluator** – Deterministic veto check + improvement feedback.
- **CriticAgent** – Deep quality analysis (overfitting, instability, risk).
- **StrategyEvolver** – Genetic-algorithm-inspired strategy evolution.
"""

from .master import MasterAgent
from .intent_parser import IntentParser, ResearchIntent
from .planner import PlannerAgent, ResearchPlan
from .critic import CriticAgent, CriticVerdict
from .evolution import StrategyEvolver

__all__ = [
    "MasterAgent",
    "IntentParser",
    "ResearchIntent",
    "PlannerAgent",
    "ResearchPlan",
    "CriticAgent",
    "CriticVerdict",
    "StrategyEvolver",
]
