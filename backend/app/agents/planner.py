"""PlannerAgent — decomposes a ResearchIntent into a structured research plan.

Decides which strategy families to explore, how many variants per family,
optimization priorities, and acceptance criteria based on the data profile
and user intent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import DataProfile
from .intent_parser import ResearchIntent


@dataclass
class ResearchPlan:
    strategy_families: List[str] = field(default_factory=list)
    n_variants_per_family: int = 2
    total_variants: int = 6
    optimization_priority: str = "sharpe"
    validation_requirements: Dict[str, bool] = field(default_factory=lambda: {
        "walk_forward": True, "monte_carlo": True, "optimization": True,
    })
    max_iterations: int = 5
    acceptance_criteria: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        families = ", ".join(self.strategy_families)
        return (
            f"Plan: {self.total_variants} variants across [{families}]. "
            f"Optimize for {self.optimization_priority}. "
            f"Max {self.max_iterations} iterations."
        )


# Strategy families and their descriptions
STRATEGY_FAMILIES = {
    "trend_following": {
        "label": "Trend Following",
        "indicators": ["ema", "sma", "macd", "supertrend", "adx"],
        "best_for": ["trending"],
        "description": "EMA crossovers, SuperTrend direction, MACD momentum",
    },
    "mean_reversion": {
        "label": "Mean Reversion",
        "indicators": ["rsi", "bollinger_bands", "stochastic", "cci"],
        "best_for": ["ranging"],
        "description": "Bollinger bounces, RSI oversold/overbought, Stoch extremes",
    },
    "momentum": {
        "label": "Momentum",
        "indicators": ["rsi", "macd", "roc", "adx"],
        "best_for": ["trending", "volatile"],
        "description": "RSI momentum, MACD histogram, ROC breakouts",
    },
    "breakout": {
        "label": "Breakout",
        "indicators": ["bollinger_bands", "atr", "adx"],
        "best_for": ["volatile", "ranging"],
        "description": "Bollinger squeeze, ATR expansion, channel breakouts",
    },
    "volatility": {
        "label": "Volatility",
        "indicators": ["atr", "bollinger_bands", "supertrend"],
        "best_for": ["volatile"],
        "description": "ATR-based entries, volatility expansion/contraction",
    },
    "vwap_anchored": {
        "label": "VWAP Anchored",
        "indicators": ["vwap", "rsi", "ema"],
        "best_for": ["trending", "ranging"],
        "description": "VWAP cross + RSI confirmation for intraday",
    },
    "ichimoku": {
        "label": "Ichimoku Cloud",
        "indicators": ["ichimoku", "rsi", "adx"],
        "best_for": ["trending"],
        "description": "Cloud breakout + Tenkan/Kijun cross",
    },
}

# Regime → prioritized family order
_REGIME_PRIORITY = {
    "trending": ["trend_following", "momentum", "ichimoku", "vwap_anchored", "breakout"],
    "ranging":  ["mean_reversion", "breakout", "vwap_anchored", "volatility", "momentum"],
    "volatile": ["momentum", "breakout", "volatility", "trend_following", "mean_reversion"],
    "unknown":  ["trend_following", "mean_reversion", "momentum", "breakout", "volatility"],
}

# Style → optimization metric
_STYLE_METRIC = {
    "scalping": "profit_factor",
    "intraday": "sharpe",
    "swing": "calmar",
    "positional": "total_return",
}


class PlannerAgent:
    """Creates a structured research plan from intent + data profile."""

    def plan(
        self,
        intent: ResearchIntent,
        profile: DataProfile,
    ) -> ResearchPlan:
        rp = ResearchPlan()

        # Select families based on regime
        regime = profile.regime if profile.regime != "unknown" else "unknown"
        priority = _REGIME_PRIORITY.get(regime, _REGIME_PRIORITY["unknown"])

        # Pick top 3-5 families (enough for 6-10 variants)
        n_families = 3 if intent.risk_tolerance == "low" else 4
        rp.strategy_families = priority[:n_families]
        rp.n_variants_per_family = 2
        rp.total_variants = min(10, n_families * rp.n_variants_per_family)

        # Optimization priority from trading style
        rp.optimization_priority = _STYLE_METRIC.get(intent.style, "sharpe")

        # Acceptance criteria from intent targets
        rp.acceptance_criteria = intent.target_metrics.copy()

        # Validation requirements
        rp.validation_requirements = {
            "walk_forward": True,
            "monte_carlo": True,
            "optimization": intent.risk_tolerance != "low",
        }

        # Iteration budget based on risk tolerance
        rp.max_iterations = {"low": 3, "medium": 5, "high": 5}.get(intent.risk_tolerance, 5)

        # Notes for the architect
        rp.notes = [
            f"Data regime: {regime} (ADX={profile.avg_adx:.1f})",
            f"Trend: {profile.trend_direction}",
            f"Volatility: ATR={profile.atr_pct:.2f}% of price",
            f"Trading style: {intent.style}",
            f"Market: {intent.market}",
        ]
        if intent.constraints:
            rp.notes.append(f"Constraints: {', '.join(intent.constraints)}")

        return rp
