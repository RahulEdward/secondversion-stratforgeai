"""MasterAgent — orchestrates the multi-agent strategy research loop.

Flow
----
1. **DataAnalyst** profiles the dataset (direct computation, ~200 ms)
2. **StrategyArchitect** designs 2-3 variants (LLM call or templates)
3. **Backtester** runs ``run_full_pipeline`` on each variant
4. **Evaluator** checks results — if passing, stop; else feed back to architect
5. Repeat steps 2-4 up to ``MAX_ITERATIONS``
6. Render report + save best strategy

The master yields WebSocket-compatible frames so the UI streams progress
in real time.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from .analyst import DataAnalyst
from .architect import StrategyArchitect
from .backtester import Backtester
from .base import DataProfile, PipelineResult
from .evaluator import Evaluator

# How many full design→test→evaluate cycles before we give up.
MAX_ITERATIONS = 5


class MasterAgent:
    """Supervisor agent that coordinates the research loop."""

    def __init__(self) -> None:
        self.analyst = DataAnalyst()
        self.architect = StrategyArchitect()
        self.backtester = Backtester()
        self.evaluator = Evaluator()

    async def run_research(
        self,
        user_request: str,
        dataset_id: str,
        provider: Any,
        model: str,
        *,
        market: str = "crypto",
        init_cash: float = 10_000.0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Full autonomous research loop. Yields streaming frames."""

        t0 = time.perf_counter()
        all_results: List[PipelineResult] = []
        best_overall: Optional[PipelineResult] = None

        # ── Phase 1: Data Reconnaissance ────────────────────────────────
        yield _text("🔍 **Phase 1 — Data Reconnaissance**\n")
        yield _text("Analyzing dataset: computing RSI, ATR, ADX, Bollinger Bands, EMAs...\n")

        try:
            profile = await self.analyst.analyze(dataset_id)
            yield _text(
                f"✅ Dataset profiled: {profile.n_bars} bars, "
                f"regime=**{profile.regime}**, trend=**{profile.trend_direction}**\n"
                f"   RSI={profile.latest_rsi:.1f}, ADX={profile.avg_adx:.1f}, "
                f"ATR={profile.atr_pct:.2f}% of price\n\n"
            )
        except Exception as exc:
            yield _text(f"❌ Data analysis failed: {exc}\n")
            yield _text("Falling back to default profile...\n\n")
            profile = DataProfile()

        feedback: Optional[str] = None

        # ── Iteration loop ──────────────────────────────────────────────
        for iteration in range(1, MAX_ITERATIONS + 1):
            yield _text(
                f"📐 **Phase 2 — Iteration {iteration}/{MAX_ITERATIONS}: "
                f"Designing Strategies**\n"
            )

            # ── Design strategies ───────────────────────────────────────
            try:
                specs = await self.architect.design(
                    profile, provider, model, feedback=feedback, market=market
                )
            except Exception as exc:
                yield _text(f"❌ Strategy design failed: {exc}\n")
                specs = self.architect._template_strategies(profile, feedback, market)

            if not specs:
                yield _text("❌ No valid strategies designed. Retrying...\n")
                continue

            for i, spec in enumerate(specs):
                yield _text(f"   Variant {i + 1}: **{spec.get('name', 'Unnamed')}**\n")
            yield _text("\n")

            # ── Run pipelines ───────────────────────────────────────────
            yield _text(f"⚡ **Phase 3 — Testing {len(specs)} Variants**\n")
            iteration_results: List[PipelineResult] = []

            for i, spec in enumerate(specs):
                name = spec.get("name", f"Variant {i + 1}")
                yield _text(f"   ⏳ Running pipeline for **{name}**...")

                opt_grid = self.architect.get_optimization_grid(spec)

                try:
                    result = await self.backtester.run(
                        spec, dataset_id,
                        optimize_grid=opt_grid,
                        init_cash=init_cash,
                        render=False,
                    )
                    iteration_results.append(result)
                    all_results.append(result)

                    # Show result inline
                    n_trades = result.metrics.get("num_trades", 0)
                    yield _text(
                        f" → Grade=**{result.grade}**, "
                        f"trades={n_trades}, "
                        f"sharpe={result.metrics.get('sharpe', '—')}, "
                        f"verdict={result.verdict}\n"
                    )
                except Exception as exc:
                    err_result = PipelineResult(
                        variant_name=name, spec=spec,
                        error=str(exc),
                    )
                    iteration_results.append(err_result)
                    yield _text(f" → ❌ Error: {exc}\n")

            yield _text("\n")

            # ── Evaluate ────────────────────────────────────────────────
            yield _text("🔎 **Phase 4 — Evaluating Results**\n")

            best, is_passing, eval_feedback = self.evaluator.evaluate(
                iteration_results
            )

            if best is not None:
                if best_overall is None or best.score > best_overall.score:
                    best_overall = best

            if is_passing and best is not None:
                yield _text(
                    f"✅ **FOUND PASSING STRATEGY!** "
                    f"**{best.variant_name}** — Grade {best.grade} "
                    f"({best.verdict})\n\n"
                )
                break
            else:
                yield _text(
                    f"❌ No variant passed. Best so far: "
                    f"**{best.variant_name if best else '—'}** "
                    f"(Grade {best.grade if best else 'F'})\n"
                )
                if iteration < MAX_ITERATIONS:
                    yield _text(
                        f"   Analyzing failures and designing improved variants...\n\n"
                    )
                    feedback = eval_feedback
                else:
                    yield _text(
                        f"\n⚠️ Reached max iterations ({MAX_ITERATIONS}). "
                        f"Finalizing best result.\n\n"
                    )

        # ── Phase 5: Finalize ───────────────────────────────────────────
        if best_overall is None:
            yield _text("❌ **No strategy produced any results.** Check dataset quality.\n")
            return

        yield _text("📊 **Phase 5 — Finalizing Best Strategy**\n")
        yield _text(f"   Best: **{best_overall.variant_name}** (Grade {best_overall.grade})\n")

        # Re-run with render=True for the report
        yield _text("   Generating report...\n")
        try:
            final = await self.backtester.run(
                best_overall.spec, dataset_id,
                init_cash=init_cash,
                render=True,
            )
            if final.report_url:
                yield _text(f"   📄 Report: {final.report_url}\n")
            best_overall = final  # Update with report URL
        except Exception as exc:
            yield _text(f"   ⚠️ Report generation failed: {exc}\n")

        # Save to library
        yield _text("   💾 Saving to strategy library...\n")
        try:
            from ..tool_exec import run_tool
            save_result = await run_tool("save_strategy", {
                "name": best_overall.variant_name,
                "description": (
                    f"Auto-researched strategy. "
                    f"Grade={best_overall.grade}, "
                    f"Sharpe={best_overall.metrics.get('sharpe', '—')}, "
                    f"Trades={best_overall.metrics.get('num_trades', 0)}"
                ),
                "backtest_id": best_overall.backtest_id,
            })
            if save_result.get("ok"):
                sid = save_result["output"].get("strategy_id", "")
                yield _text(f"   ✅ Saved as strategy_id: {sid}\n")
            else:
                yield _text(f"   ⚠️ Save: {save_result.get('error', '?')}\n")
        except Exception as exc:
            yield _text(f"   ⚠️ Save failed: {exc}\n")

        # ── Final Summary ───────────────────────────────────────────────
        elapsed = time.perf_counter() - t0
        yield _text(self._format_summary(best_overall, all_results, elapsed))

    # ------------------------------------------------------------------ #

    def _format_summary(
        self,
        best: PipelineResult,
        all_results: List[PipelineResult],
        elapsed: float,
    ) -> str:
        """Build the final summary table."""
        m = best.metrics
        lines = [
            "\n---\n",
            "## 🏆 Research Complete\n\n",
            f"**Strategy:** {best.variant_name}\n",
            f"**Grade:** {best.grade} | **Verdict:** {best.verdict} | "
            f"**Score:** {best.score:.1f}\n\n",
            "### Key Metrics\n",
            f"| Metric | Value |\n",
            f"|--------|-------|\n",
            f"| Sharpe | {_fmt(m.get('sharpe'))} |\n",
            f"| Sortino | {_fmt(m.get('sortino'))} |\n",
            f"| Profit Factor | {_fmt(m.get('profit_factor'))} |\n",
            f"| Win Rate | {_pct(m.get('win_rate'))} |\n",
            f"| Max Drawdown | {_pct(m.get('max_drawdown'))} |\n",
            f"| Total Return | {_pct(m.get('total_return'))} |\n",
            f"| Num Trades | {m.get('num_trades', 0)} |\n",
        ]

        if best.wfe is not None:
            lines.append(f"| Walk-Forward Efficiency | {best.wfe:.2f} |\n")
        if best.mc_survival is not None:
            lines.append(f"| MC Survival Rate | {best.mc_survival:.1%} |\n")
        if best.mc_p_value is not None:
            lines.append(f"| MC p-value | {best.mc_p_value:.4f} |\n")

        if best.report_url:
            lines.append(f"\n📄 **Report:** {best.report_url}\n")

        # Vetos
        if best.vetos:
            lines.append("\n### Veto Checks\n")
            for v in best.vetos:
                lines.append(f"- ⚠️ **{v.get('rule', '?')}**: {v.get('message', '?')}\n")

        lines.append(
            f"\n*Tested {len(all_results)} variants in {elapsed:.1f}s*\n"
        )
        return "".join(lines)


# ─── Helpers ────────────────────────────────────────────────────────────


def _text(delta: str) -> Dict[str, Any]:
    """Create a text streaming frame."""
    return {"type": "text", "delta": delta}


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return "—"


def _pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"
