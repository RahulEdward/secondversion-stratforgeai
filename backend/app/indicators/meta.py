"""Indicator use-case metadata for intelligent skill selection.

Each indicator has: use_case categories, best market regimes,
incompatible indicators (redundant), parameter flexibility, and signal type.
The StrategyArchitect uses this to select indicators logically, not randomly.
"""
from __future__ import annotations

from typing import Any, Dict, List

INDICATOR_META: Dict[str, Dict[str, Any]] = {
    "rsi": {
        "use_case": ["mean_reversion", "overbought_oversold", "momentum"],
        "best_for": ["ranging", "volatile"],
        "incompatible_with": ["stochastic", "williams_r"],
        "param_flexibility": "high",
        "signal_type": "oscillator",
        "default_entry_ops": [("<", 40), (">", 60)],
        "description": "Relative Strength Index — momentum oscillator",
    },
    "ema": {
        "use_case": ["trend_following", "support_resistance", "crossover"],
        "best_for": ["trending"],
        "incompatible_with": ["sma"],
        "param_flexibility": "high",
        "signal_type": "overlay",
        "default_entry_ops": [("crosses_above", "ref:ema"), (">", "ref:close")],
        "description": "Exponential Moving Average — trend overlay",
    },
    "sma": {
        "use_case": ["trend_following", "support_resistance"],
        "best_for": ["trending"],
        "incompatible_with": ["ema"],
        "param_flexibility": "high",
        "signal_type": "overlay",
        "description": "Simple Moving Average — trend overlay",
    },
    "macd": {
        "use_case": ["trend_following", "momentum", "crossover"],
        "best_for": ["trending", "volatile"],
        "incompatible_with": [],
        "param_flexibility": "medium",
        "signal_type": "oscillator",
        "description": "MACD — trend momentum oscillator",
    },
    "bollinger_bands": {
        "use_case": ["mean_reversion", "volatility", "breakout"],
        "best_for": ["ranging", "volatile"],
        "incompatible_with": [],
        "param_flexibility": "medium",
        "signal_type": "overlay",
        "description": "Bollinger Bands — volatility envelope",
    },
    "supertrend": {
        "use_case": ["trend_following", "trailing_stop"],
        "best_for": ["trending"],
        "incompatible_with": [],
        "param_flexibility": "medium",
        "signal_type": "overlay",
        "description": "SuperTrend — ATR-based trend indicator",
    },
    "adx": {
        "use_case": ["trend_strength", "regime_filter"],
        "best_for": ["trending", "ranging"],
        "incompatible_with": [],
        "param_flexibility": "low",
        "signal_type": "oscillator",
        "description": "ADX — trend strength (not direction)",
    },
    "atr": {
        "use_case": ["volatility", "stop_sizing", "position_sizing"],
        "best_for": ["trending", "volatile", "ranging"],
        "incompatible_with": [],
        "param_flexibility": "low",
        "signal_type": "auxiliary",
        "description": "ATR — volatility measure for stops/sizing",
    },
    "stochastic": {
        "use_case": ["mean_reversion", "overbought_oversold"],
        "best_for": ["ranging"],
        "incompatible_with": ["rsi", "williams_r"],
        "param_flexibility": "medium",
        "signal_type": "oscillator",
        "description": "Stochastic — momentum oscillator",
    },
    "vwap": {
        "use_case": ["intraday_anchor", "mean_reversion"],
        "best_for": ["trending", "ranging"],
        "incompatible_with": [],
        "param_flexibility": "low",
        "signal_type": "overlay",
        "description": "VWAP — volume-weighted average price",
    },
    "ichimoku": {
        "use_case": ["trend_following", "support_resistance", "crossover"],
        "best_for": ["trending"],
        "incompatible_with": [],
        "param_flexibility": "low",
        "signal_type": "overlay",
        "description": "Ichimoku Cloud — multi-signal trend system",
    },
    "obv": {
        "use_case": ["volume_confirmation", "divergence"],
        "best_for": ["trending", "ranging"],
        "incompatible_with": [],
        "param_flexibility": "low",
        "signal_type": "auxiliary",
        "description": "On-Balance Volume — volume-based trend confirmation",
    },
    "williams_r": {
        "use_case": ["mean_reversion", "overbought_oversold"],
        "best_for": ["ranging"],
        "incompatible_with": ["rsi", "stochastic"],
        "param_flexibility": "medium",
        "signal_type": "oscillator",
        "description": "Williams %R — momentum oscillator",
    },
    "roc": {
        "use_case": ["momentum", "breakout"],
        "best_for": ["trending", "volatile"],
        "incompatible_with": [],
        "param_flexibility": "medium",
        "signal_type": "oscillator",
        "description": "Rate of Change — momentum measure",
    },
    "cci": {
        "use_case": ["mean_reversion", "breakout"],
        "best_for": ["ranging", "volatile"],
        "incompatible_with": ["rsi"],
        "param_flexibility": "medium",
        "signal_type": "oscillator",
        "description": "CCI — identifies cyclical turns",
    },
}


def indicators_for_regime(regime: str) -> List[str]:
    """Return indicator names best suited for a market regime."""
    return [
        name for name, meta in INDICATOR_META.items()
        if regime in meta["best_for"]
    ]


def compatible_pair(ind_a: str, ind_b: str) -> bool:
    """Check if two indicators are compatible (not redundant)."""
    meta_a = INDICATOR_META.get(ind_a, {})
    return ind_b not in meta_a.get("incompatible_with", [])


def select_diverse_set(regime: str, n: int = 3) -> List[str]:
    """Select N diverse indicators for a regime, avoiding redundancy."""
    candidates = indicators_for_regime(regime)
    if not candidates:
        candidates = list(INDICATOR_META.keys())

    selected: List[str] = []
    signal_types_used: set = set()

    for ind in candidates:
        meta = INDICATOR_META[ind]
        # Prefer diverse signal types
        if meta["signal_type"] in signal_types_used and len(selected) < n:
            continue
        # Check compatibility with already selected
        if all(compatible_pair(ind, s) for s in selected):
            selected.append(ind)
            signal_types_used.add(meta["signal_type"])
        if len(selected) >= n:
            break

    # Fill remaining slots if needed
    for ind in candidates:
        if ind not in selected and len(selected) < n:
            if all(compatible_pair(ind, s) for s in selected):
                selected.append(ind)
        if len(selected) >= n:
            break

    return selected[:n]
