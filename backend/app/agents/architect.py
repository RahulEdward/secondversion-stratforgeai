"""StrategyArchitect agent — designs strategy specs via an LLM call.

This is the ONLY agent that uses an LLM. It receives a DataProfile (from
the analyst) and optional failure feedback (from previous iterations),
then outputs 2-3 structurally different StrategySpec JSON dicts.

The system prompt is tightly scoped: produce valid JSON, nothing else.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .base import DataProfile, PipelineResult


# ── Template strategies by regime ──────────────────────────────────────
# Pre-built specs the architect can fall back on if the LLM produces
# garbage. Also used as examples in the system prompt.

_TREND_STRATEGY = {
    "name": "EMA Crossover + ADX Filter",
    "market": "crypto",
    "entries": {
        "all_of": [
            {"indicator": "ema", "params": {"period": 20}, "op": ">",
             "ref_indicator": "ema", "ref_params": {"period": 50}},
            {"indicator": "adx", "params": {"period": 14}, "field": "adx",
             "op": ">", "value": 20},
        ]
    },
    "exits": {
        "any_of": [
            {"indicator": "ema", "params": {"period": 20}, "op": "<",
             "ref_indicator": "ema", "ref_params": {"period": 50}},
        ]
    },
    "stops": {
        "stop_loss": {"type": "atr", "multiplier": 2.0, "period": 14},
        "take_profit": {"type": "fixed_pct", "value": 0.04},
        "trailing": {"type": "trailing_pct", "value": 0.025},
    },
    "sizing": {"type": "fixed_pct", "value": 0.95},
    "fees_override": 0.001,
    "slippage_override": 0.0005,
}

_MEANREV_STRATEGY = {
    "name": "Bollinger Mean Reversion + RSI",
    "market": "crypto",
    "entries": {
        "all_of": [
            {"indicator": "rsi", "params": {"period": 14}, "op": "<", "value": 40},
            {"indicator": "bollinger_bands", "params": {"period": 20, "std_dev": 2.0},
             "field": "pct_b", "op": "<", "value": 0.2},
        ]
    },
    "exits": {
        "any_of": [
            {"indicator": "rsi", "params": {"period": 14}, "op": ">", "value": 60},
            {"indicator": "bollinger_bands", "params": {"period": 20, "std_dev": 2.0},
             "field": "pct_b", "op": ">", "value": 0.8},
        ]
    },
    "stops": {
        "stop_loss": {"type": "atr", "multiplier": 1.5, "period": 14},
        "take_profit": {"type": "fixed_pct", "value": 0.03},
    },
    "sizing": {"type": "fixed_pct", "value": 0.95},
    "fees_override": 0.001,
    "slippage_override": 0.0005,
}

_MOMENTUM_STRATEGY = {
    "name": "SuperTrend Momentum + RSI Confirmation",
    "market": "crypto",
    "entries": {
        "all_of": [
            {"indicator": "supertrend", "params": {"period": 10, "multiplier": 3.0},
             "field": "direction", "op": "==", "value": 1},
            {"indicator": "rsi", "params": {"period": 14}, "op": ">", "value": 50},
        ]
    },
    "exits": {
        "any_of": [
            {"indicator": "supertrend", "params": {"period": 10, "multiplier": 3.0},
             "field": "direction", "op": "==", "value": -1},
        ]
    },
    "stops": {
        "stop_loss": {"type": "atr", "multiplier": 2.5, "period": 14},
        "take_profit": {"type": "fixed_pct", "value": 0.05},
        "trailing": {"type": "trailing_pct", "value": 0.03},
    },
    "sizing": {"type": "fixed_pct", "value": 0.95},
    "fees_override": 0.001,
    "slippage_override": 0.0005,
}

_FALLBACK_STRATEGIES = {
    "trending": [_TREND_STRATEGY, _MOMENTUM_STRATEGY],
    "ranging": [_MEANREV_STRATEGY, _TREND_STRATEGY],
    "volatile": [_MOMENTUM_STRATEGY, _MEANREV_STRATEGY],
    "unknown": [_TREND_STRATEGY, _MEANREV_STRATEGY, _MOMENTUM_STRATEGY],
}


# Optimization grids matched to each strategy type
_OPTIMIZATION_GRIDS = {
    "EMA Crossover + ADX Filter": {
        "entries.all_of.0.params.period": [15, 20, 25],
        "entries.all_of.1.value": [15, 20, 25],
        "stops.stop_loss.multiplier": [1.5, 2.0, 2.5],
    },
    "Bollinger Mean Reversion + RSI": {
        "entries.all_of.0.value": [35, 40, 45],
        "exits.any_of.0.value": [55, 60, 65],
        "stops.stop_loss.multiplier": [1.0, 1.5, 2.0],
    },
    "SuperTrend Momentum + RSI Confirmation": {
        "entries.all_of.0.params.multiplier": [2.0, 3.0, 4.0],
        "entries.all_of.1.value": [45, 50, 55],
        "stops.stop_loss.multiplier": [2.0, 2.5, 3.0],
    },
}


_ARCHITECT_SYSTEM_PROMPT = """\
You are a quant strategy architect. You receive a DATA PROFILE and optionally
FEEDBACK from failed previous attempts. Output ONLY a JSON array of 2-3
strategy spec objects. No explanation, no markdown, no code fences — just
the raw JSON array.

Rules:
1. Each strategy must be STRUCTURALLY DIFFERENT (different indicator families)
2. Use LOOSE thresholds that generate trades (RSI < 45 not < 30, ADX > 18 not > 30)
3. Always include stops (stop_loss + take_profit), sizing, fees_override, slippage_override
4. Market field: use "crypto" for crypto data, "equity" for stocks, "forex" for FX
5. Valid indicators: rsi, macd, bollinger_bands, supertrend, adx, atr, ema, sma,
   stochastic, vwap, ichimoku, donchian_channel, roc, williams_r, cci, obv, mfi
6. Valid ops: "<", ">", "<=", ">=", "==", "crosses_above", "crosses_below"
7. Each entries/exits must be a CondGroup: {"all_of": [...]} or {"any_of": [...]}
8. Entry conditions should use "all_of" (AND), exit conditions should use "any_of" (OR)

Example strategy spec:
{
  "name": "EMA Crossover Trend",
  "market": "crypto",
  "entries": {"all_of": [
    {"indicator": "ema", "params": {"period": 20}, "op": ">",
     "ref_indicator": "ema", "ref_params": {"period": 50}},
    {"indicator": "adx", "params": {"period": 14}, "field": "adx", "op": ">", "value": 20}
  ]},
  "exits": {"any_of": [
    {"indicator": "ema", "params": {"period": 20}, "op": "<",
     "ref_indicator": "ema", "ref_params": {"period": 50}}
  ]},
  "stops": {
    "stop_loss": {"type": "atr", "multiplier": 2.0, "period": 14},
    "take_profit": {"type": "fixed_pct", "value": 0.04},
    "trailing": {"type": "trailing_pct", "value": 0.025}
  },
  "sizing": {"type": "fixed_pct", "value": 0.95},
  "fees_override": 0.001,
  "slippage_override": 0.0005
}
"""


class StrategyArchitect:
    """Designs strategy variants — uses LLM when available, falls back
    to templates when LLM fails or is unavailable."""

    async def design(
        self,
        profile: DataProfile,
        provider: Any = None,
        model: str = "",
        feedback: Optional[str] = None,
        market: str = "crypto",
    ) -> List[Dict[str, Any]]:
        """Return 2-3 strategy spec dicts.

        Tries LLM first; falls back to curated templates on failure.
        """
        # Try LLM if available
        if provider is not None and model:
            try:
                specs = await self._design_with_llm(
                    profile, provider, model, feedback, market
                )
                if specs and len(specs) >= 1:
                    return specs
            except Exception:
                pass  # Fall through to templates

        # Fallback: curated templates based on regime
        return self._template_strategies(profile, feedback, market)

    async def _design_with_llm(
        self,
        profile: DataProfile,
        provider: Any,
        model: str,
        feedback: Optional[str],
        market: str,
    ) -> List[Dict[str, Any]]:
        """Single LLM call to generate strategy specs."""
        user_msg = f"DATA PROFILE:\n{profile.summary()}\nMarket: {market}\n"
        if feedback:
            user_msg += f"\nFEEDBACK FROM FAILED ATTEMPTS:\n{feedback}\n"
        user_msg += "\nDesign 2-3 strategy specs. Output ONLY the JSON array."

        messages = [{"role": "user", "content": [{"type": "text", "text": user_msg}]}]
        full_text = ""

        async for chunk in provider.stream_chat(
            messages=messages,
            tools=[],
            model=model,
            system=_ARCHITECT_SYSTEM_PROMPT,
        ):
            if chunk.get("type") == "text":
                full_text += chunk.get("delta", "")

        return self._parse_specs(full_text, market)

    def _parse_specs(self, raw: str, market: str) -> List[Dict[str, Any]]:
        """Extract JSON array from LLM output — tolerant of markdown fences."""
        # Strip code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = cleaned.strip().rstrip("`")

        # Try to find a JSON array
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1:
            return []

        try:
            specs = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return []

        if not isinstance(specs, list):
            return []

        # Validate and fix each spec
        valid = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            spec.setdefault("market", market)
            spec.setdefault("fees_override", 0.001)
            spec.setdefault("slippage_override", 0.0005)
            spec.setdefault("sizing", {"type": "fixed_pct", "value": 0.95})
            if "entries" in spec and "exits" in spec:
                valid.append(spec)
        return valid[:3]

    def _template_strategies(
        self,
        profile: DataProfile,
        feedback: Optional[str],
        market: str,
    ) -> List[Dict[str, Any]]:
        """Return pre-built template strategies based on regime."""
        import copy

        templates = _FALLBACK_STRATEGIES.get(profile.regime, _FALLBACK_STRATEGIES["unknown"])
        result = []
        for t in templates:
            spec = copy.deepcopy(t)
            spec["market"] = market
            result.append(spec)
        return result

    @staticmethod
    def get_optimization_grid(spec: Dict[str, Any]) -> Optional[Dict[str, list]]:
        """Return a sensible optimization grid for a strategy, or None."""
        name = spec.get("name", "")
        grid = _OPTIMIZATION_GRIDS.get(name)
        if grid:
            return grid
        # Generic fallback grid — sweep stop loss multiplier
        return {
            "stops.stop_loss.multiplier": [1.5, 2.0, 2.5, 3.0],
        }
