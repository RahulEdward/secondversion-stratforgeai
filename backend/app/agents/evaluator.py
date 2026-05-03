"""Evaluator agent — deterministic verdict check + improvement feedback.

No LLM needed: analyses pipeline results, picks the best variant, and
generates structured feedback for the architect to design the next
iteration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import PipelineResult


class Evaluator:
    """Deterministic evaluation of pipeline results."""

    def evaluate(
        self,
        results: List[PipelineResult],
        *,
        min_grade: str = "B-",
    ) -> Tuple[Optional[PipelineResult], bool, str]:
        """Evaluate all pipeline results from one iteration.

        Returns:
            (best_result, is_passing, feedback_for_architect)
        """
        if not results:
            return None, False, "No results to evaluate."

        # Filter out errored results
        valid = [r for r in results if r.error is None]
        if not valid:
            errors = "; ".join(
                f"{r.variant_name}: {r.error}" for r in results
            )
            return None, False, f"All variants errored: {errors}"

        # Sort by score (highest first)
        valid.sort(key=lambda r: r.score, reverse=True)
        best = valid[0]

        # Check if best passes
        if best.passing:
            return best, True, ""

        # Not passing — build improvement feedback
        feedback = self._build_feedback(valid)
        return best, False, feedback

    def _build_feedback(self, results: List[PipelineResult]) -> str:
        """Analyze failures and generate actionable feedback."""
        lines: List[str] = []

        for r in results:
            lines.append(f"--- {r.variant_name} ---")
            lines.append(r.failure_summary())

            # Specific advice based on vetos
            for v in r.vetos:
                rule = v.get("rule", "")
                advice = _VETO_ADVICE.get(rule)
                if advice:
                    lines.append(f"  FIX: {advice}")

            # Additional checks
            n_trades = r.metrics.get("num_trades", 0)
            if n_trades == 0:
                lines.append(
                    "  CRITICAL: Zero trades — entry conditions never fire. "
                    "Use much looser thresholds (RSI < 50, ADX > 15) or "
                    "different indicators that trigger more often."
                )
            elif n_trades < 20:
                lines.append(
                    f"  WARNING: Only {n_trades} trades — loosen entry "
                    "thresholds significantly or use faster indicators."
                )

            pf = r.metrics.get("profit_factor")
            if pf is not None and pf < 1.0:
                lines.append(
                    "  CRITICAL: Profit factor < 1.0 — strategy loses money. "
                    "Try a completely different indicator combination, "
                    "not just parameter tweaks."
                )

            if r.wfe is not None and r.wfe < 0.3:
                lines.append(
                    "  WARNING: WFE < 0.3 — severe overfitting. Simplify "
                    "the strategy (fewer conditions, wider stop ranges)."
                )

        return "\n".join(lines)


# Mapping from veto rule names to actionable fix suggestions
_VETO_ADVICE: Dict[str, str] = {
    "min_trades": (
        "Loosen entry conditions — use RSI < 45 (not 30), "
        "ADX > 15 (not 25), or use cross-based signals that fire more."
    ),
    "data_usage": (
        "Strategy never holds a position. Entry conditions are "
        "impossible to satisfy simultaneously — simplify to fewer conditions."
    ),
    "max_drawdown": (
        "Tighten stop-loss (reduce ATR multiplier), add trailing stop, "
        "or reduce position size."
    ),
    "profit_factor": (
        "No edge — try a fundamentally different strategy type "
        "(switch from trend to mean-reversion or vice versa)."
    ),
    "mc_survival": (
        "Edge is noise-driven — add a regime filter (ADX for trends, "
        "Bollinger width for mean-reversion) to avoid choppy markets."
    ),
    "wfe_overfit": (
        "Strategy is curve-fit — use fewer entry conditions and "
        "wider parameter ranges in optimization."
    ),
}
