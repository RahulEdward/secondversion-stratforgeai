"""StrategyEvolver — evolves strategy specs between iterations.

Uses genetic-algorithm-inspired operations: parameter mutation, indicator
swap, condition addition/removal, crossover, and stop adjustment.
Top strategies pass through unchanged (elitism).
"""
from __future__ import annotations

import copy
import random
from typing import Any, Dict, List, Optional

from .base import PipelineResult
from .critic import CriticVerdict


# Indicator compatibility groups — swaps happen within the same group
_INDICATOR_GROUPS = {
    "trend_overlay": ["ema", "sma", "supertrend", "ichimoku"],
    "momentum_osc": ["rsi", "stochastic", "williams_r", "cci", "roc"],
    "volatility": ["bollinger_bands", "atr"],
    "volume": ["obv", "vwap"],
    "directional": ["adx", "macd"],
}

# Reverse lookup: indicator → group
_IND_TO_GROUP: Dict[str, str] = {}
for _grp, _inds in _INDICATOR_GROUPS.items():
    for _ind in _inds:
        _IND_TO_GROUP[_ind] = _grp


class StrategyEvolver:
    """Evolves strategy specs using feedback from Critic and results."""

    def evolve(
        self,
        parent_specs: List[Dict[str, Any]],
        results: List[PipelineResult],
        critic_verdicts: List[CriticVerdict],
        generation: int,
        market: str = "crypto",
    ) -> List[Dict[str, Any]]:
        """Produce next-gen specs from parents + feedback.

        Returns 2-4 evolved variants (the Architect adds 2-3 new ones).
        """
        if not parent_specs:
            return []

        # Pair specs with results and verdicts
        paired = list(zip(parent_specs, results, critic_verdicts))
        # Sort by pipeline score (best first)
        paired.sort(key=lambda x: x[1].score, reverse=True)

        evolved: List[Dict[str, Any]] = []

        # 1. Elitism: top 1 spec passes through unchanged
        best_spec, best_result, best_verdict = paired[0]
        elite = copy.deepcopy(best_spec)
        elite["name"] = f"{elite.get('name', 'Elite')} (Gen{generation} Elite)"
        evolved.append(elite)

        # 2. Mutate the best spec based on Critic feedback
        if best_verdict.improvements:
            mutated = self._apply_improvements(
                copy.deepcopy(best_spec), best_verdict, best_result
            )
            mutated["name"] = f"{best_spec.get('name', 'Mutated')} (Gen{generation} Improved)"
            evolved.append(mutated)

        # 3. Crossover: combine best entries with second-best exits (if available)
        if len(paired) >= 2:
            spec_a = paired[0][0]
            spec_b = paired[1][0]
            child = self._crossover(spec_a, spec_b, generation)
            if child:
                evolved.append(child)

        # 4. Parameter mutation on second-best
        if len(paired) >= 2:
            second = copy.deepcopy(paired[1][0])
            mutated2 = self._mutate_params(second)
            mutated2["name"] = f"{second.get('name', 'Mutated')} (Gen{generation} ParamTweak)"
            evolved.append(mutated2)

        return evolved[:4]  # Cap at 4 evolved variants

    def _apply_improvements(
        self,
        spec: Dict[str, Any],
        verdict: CriticVerdict,
        result: PipelineResult,
    ) -> Dict[str, Any]:
        """Apply Critic improvements to a spec."""
        # Check which categories have issues
        issue_cats = {i["category"] for i in verdict.issues}

        # Risk control fixes
        if "risk_control" in issue_cats:
            stops = spec.setdefault("stops", {})
            if not stops.get("stop_loss"):
                stops["stop_loss"] = {"type": "atr", "multiplier": 2.0, "period": 14}
            if not stops.get("take_profit"):
                stops["take_profit"] = {"type": "fixed_pct", "value": 0.04}
            if not stops.get("trailing"):
                stops["trailing"] = {"type": "trailing_pct", "value": 0.025}

        # Instability fixes
        if "instability" in issue_cats:
            # Reduce position size
            sizing = spec.setdefault("sizing", {})
            current_val = sizing.get("value", 1.0)
            if current_val > 0.80:
                sizing["value"] = 0.70

            # Tighten stop loss
            stops = spec.get("stops", {})
            sl = stops.get("stop_loss", {})
            if sl.get("type") == "atr" and sl.get("multiplier", 2.0) > 2.0:
                sl["multiplier"] = max(1.5, sl["multiplier"] - 0.5)
            elif sl.get("type") == "fixed_pct" and sl.get("value", 0.03) > 0.02:
                sl["value"] = max(0.015, sl["value"] - 0.01)

        # Overfitting fixes — simplify
        if "overfitting" in issue_cats:
            entries = spec.get("entries", {})
            # Remove one condition if too many
            for key in ("all_of", "any_of"):
                conds = entries.get(key, [])
                if len(conds) > 2:
                    # Remove the last condition (usually added filter)
                    entries[key] = conds[:2]

        # Structure fixes — add regime filter if missing
        if "structure" in issue_cats and not spec.get("regime_filter"):
            spec["regime_filter"] = {
                "indicator": "adx", "params": {"period": 14},
                "field": "adx", "op": ">", "value": 20,
            }

        return spec

    def _crossover(
        self, spec_a: Dict, spec_b: Dict, generation: int
    ) -> Optional[Dict[str, Any]]:
        """Combine entries from A with exits/stops from B."""
        child = copy.deepcopy(spec_a)
        child["exits"] = copy.deepcopy(spec_b.get("exits", child.get("exits", {})))
        child["stops"] = copy.deepcopy(spec_b.get("stops", child.get("stops", {})))

        name_a = spec_a.get("name", "A")
        name_b = spec_b.get("name", "B")
        child["name"] = f"Crossover ({name_a} × {name_b}) Gen{generation}"
        return child

    def _mutate_params(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Random-walk numeric parameters by ±15-25%."""
        for group_key in ("entries", "exits"):
            group = spec.get(group_key, {})
            for cond_key in ("all_of", "any_of"):
                conds = group.get(cond_key, [])
                for cond in conds:
                    if not isinstance(cond, dict) or "indicator" not in cond:
                        continue
                    # Mutate threshold value
                    if "value" in cond and isinstance(cond["value"], (int, float)):
                        delta = cond["value"] * random.uniform(-0.2, 0.2)
                        cond["value"] = round(cond["value"] + delta, 2)
                    # Mutate indicator params
                    params = cond.get("params", {})
                    for pk, pv in params.items():
                        if isinstance(pv, int) and pk == "period":
                            shift = max(1, int(pv * random.uniform(-0.15, 0.15)))
                            params[pk] = max(2, pv + random.choice([-shift, shift]))
                        elif isinstance(pv, float):
                            params[pk] = round(pv * random.uniform(0.8, 1.2), 3)

        # Mutate stop values
        stops = spec.get("stops", {})
        for stop_key in ("stop_loss", "take_profit", "trailing"):
            stop = stops.get(stop_key, {})
            if isinstance(stop, dict):
                if "value" in stop and isinstance(stop["value"], (int, float)):
                    stop["value"] = round(stop["value"] * random.uniform(0.8, 1.2), 4)
                if "multiplier" in stop and isinstance(stop["multiplier"], (int, float)):
                    stop["multiplier"] = round(stop["multiplier"] * random.uniform(0.85, 1.15), 2)

        return spec
