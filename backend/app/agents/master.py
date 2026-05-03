"""MasterAgent — orchestrates the full multi-agent strategy research loop.

Upgraded Flow
-------------
1. **IntentParser** parses user request → ResearchIntent
2. **DataAnalyst** profiles the dataset → DataProfile
3. **PlannerAgent** creates research plan → ResearchPlan
4. **StrategyArchitect** designs N variants per plan
5. **Backtester** runs ``run_full_pipeline`` on each variant
6. **Evaluator** checks results with hard metric gates
7. **CriticAgent** deep-analyzes quality (overfitting, instability, risk)
8. **StrategyEvolver** evolves best specs for next iteration
9. Repeat 4-8 up to ``max_iterations``
10. Render report + save best strategy

The master yields WebSocket-compatible frames so the UI streams progress.
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
from .critic import CriticAgent, CriticVerdict
from .evaluator import Evaluator
from .evolution import StrategyEvolver
from .intent_parser import IntentParser, ResearchIntent
from .planner import PlannerAgent, ResearchPlan


class MasterAgent:
    """Supervisor agent that coordinates the full research loop."""

    def __init__(self) -> None:
        self.intent_parser = IntentParser()
        self.analyst = DataAnalyst()
        self.planner = PlannerAgent()
        self.architect = StrategyArchitect()
        self.backtester = Backtester()
        self.evaluator = Evaluator()
        self.critic = CriticAgent()
        self.evolver = StrategyEvolver()

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
        best_critic: Optional[CriticVerdict] = None

        # ── Step 1: Intent Parsing ──────────────────────────────────────
        yield _text("🧠 **Step 1 — Understanding Your Request**\n")
        intent = self.intent_parser.parse(user_request)
        if intent.market != "crypto":
            market = intent.market
        yield _text(
            f"   Market: **{intent.market}** | Style: **{intent.style}** | "
            f"Risk: **{intent.risk_tolerance}** | Timeframe: **{intent.timeframe}**\n"
            f"   Targets: Sharpe≥{intent.target_metrics.get('min_sharpe', 1.0)}, "
            f"MaxDD≤{abs(intent.target_metrics.get('max_dd', -0.30)):.0%}, "
            f"PF≥{intent.target_metrics.get('min_pf', 1.2)}\n\n"
        )

        # ── Step 2: Data Reconnaissance ─────────────────────────────────
        yield _text("🔍 **Step 2 — Data Reconnaissance**\n")
        yield _text("   Computing RSI, ATR, ADX, Bollinger, EMAs...\n")
        try:
            profile = await self.analyst.analyze(dataset_id)
            yield _text(
                f"   ✅ {profile.n_bars} bars | Regime=**{profile.regime}** | "
                f"Trend=**{profile.trend_direction}**\n"
                f"   RSI={profile.latest_rsi:.1f}, ADX={profile.avg_adx:.1f}, "
                f"ATR={profile.atr_pct:.2f}%\n\n"
            )
        except Exception as exc:
            yield _text(f"   ❌ Analysis failed: {exc}. Using defaults.\n\n")
            profile = DataProfile()

        # ── Step 3: Research Planning ───────────────────────────────────
        yield _text("📐 **Step 3 — Creating Research Plan**\n")
        plan = self.planner.plan(intent, profile)
        families_str = ", ".join(plan.strategy_families)
        yield _text(
            f"   Families: [{families_str}]\n"
            f"   Variants: **{plan.total_variants}** | "
            f"Max iterations: **{plan.max_iterations}** | "
            f"Optimize for: **{plan.optimization_priority}**\n\n"
        )

        feedback: Optional[str] = None
        prev_specs: List[Dict] = []
        prev_results: List[PipelineResult] = []
        prev_verdicts: List[CriticVerdict] = []

        # ── Iteration loop ──────────────────────────────────────────────
        for iteration in range(1, plan.max_iterations + 1):
            yield _text(
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 **Iteration {iteration}/{plan.max_iterations}**\n\n"
            )

            # ── Step 4: Design strategies ───────────────────────────────
            yield _text("🏗️ **Step 4 — Designing Strategies**\n")

            # New designs from architect
            try:
                new_specs = await self.architect.design(
                    profile, provider, model, feedback=feedback, market=market
                )
            except Exception as exc:
                yield _text(f"   ❌ LLM design failed: {exc}\n")
                new_specs = self.architect._template_strategies(profile, feedback, market)

            # Evolved variants from previous iteration
            evolved_specs: List[Dict] = []
            if prev_specs and prev_results and prev_verdicts:
                try:
                    evolved_specs = self.evolver.evolve(
                        prev_specs, prev_results, prev_verdicts, iteration, market
                    )
                    yield _text(f"   🧬 Evolved {len(evolved_specs)} variants from previous iteration\n")
                except Exception as exc:
                    yield _text(f"   ⚠️ Evolution failed: {exc}\n")

            # Combine new + evolved
            specs = evolved_specs + new_specs
            if not specs:
                yield _text("   ❌ No strategies generated. Retrying...\n\n")
                continue

            # Cap at plan.total_variants
            specs = specs[:plan.total_variants]

            for i, spec in enumerate(specs):
                yield _text(f"   {i+1}. **{spec.get('name', f'Variant {i+1}')}**\n")
            yield _text(f"   Total: {len(specs)} variants\n\n")

            # ── Step 5: Backtest all variants ───────────────────────────
            yield _text(f"⚡ **Step 5 — Testing {len(specs)} Variants**\n")
            iteration_results: List[PipelineResult] = []

            for i, spec in enumerate(specs):
                name = spec.get("name", f"Variant {i+1}")
                yield _text(f"   ⏳ [{i+1}/{len(specs)}] **{name}**...")

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

                    n_trades = result.metrics.get("num_trades", 0)
                    yield _text(
                        f" Grade=**{result.grade}** | "
                        f"Trades={n_trades} | "
                        f"Sharpe={_fmt(result.metrics.get('sharpe'))} | "
                        f"PF={_fmt(result.metrics.get('profit_factor'))}\n"
                    )
                except Exception as exc:
                    err_result = PipelineResult(
                        variant_name=name, spec=spec, error=str(exc),
                    )
                    iteration_results.append(err_result)
                    yield _text(f" ❌ {exc}\n")

            yield _text("\n")

            # ── Step 6: Evaluate ────────────────────────────────────────
            yield _text("📊 **Step 6 — Evaluating Results**\n")
            best, is_passing, eval_feedback = self.evaluator.evaluate(iteration_results)

            if best is not None and (best_overall is None or best.score > best_overall.score):
                best_overall = best

            # ── Step 7: Critic Review ───────────────────────────────────
            yield _text("🔎 **Step 7 — Critic Deep Analysis**\n")
            valid_results = [r for r in iteration_results if r.error is None]
            critic_verdicts = self.critic.review_batch(valid_results, profile)

            accepted = []
            improved = []
            rejected = []
            for r, v in zip(valid_results, critic_verdicts):
                if v.decision == "accept":
                    accepted.append((r, v))
                elif v.decision == "improve":
                    improved.append((r, v))
                else:
                    rejected.append((r, v))

            yield _text(
                f"   ✅ Accepted: {len(accepted)} | "
                f"🔧 Improve: {len(improved)} | "
                f"❌ Rejected: {len(rejected)}\n"
            )

            # Show critic issues for top variant
            if critic_verdicts:
                top_v = critic_verdicts[0] if critic_verdicts else None
                if top_v and top_v.issues:
                    for issue in top_v.issues[:3]:
                        yield _text(f"   ⚠️ {issue.get('category', '?')}: {issue.get('detail', '')}\n")

            yield _text("\n")

            # If any accepted, we're done
            if accepted:
                best_r, best_v = accepted[0]
                if best_overall is None or best_r.score > best_overall.score:
                    best_overall = best_r
                    best_critic = best_v

                yield _text(
                    f"🎯 **STRATEGY ACCEPTED!** "
                    f"**{best_r.variant_name}** — Grade {best_r.grade}\n"
                    f"   Critic: overfit={best_v.overfitting_score:.2f}, "
                    f"instability={best_v.instability_score:.2f}, "
                    f"risk_control={best_v.risk_control_score:.2f}\n\n"
                )
                break

            # Prepare feedback for next iteration
            if iteration < plan.max_iterations:
                # Build combined feedback from evaluator + critic
                feedback_parts = [eval_feedback] if eval_feedback else []
                for r, v in improved[:2]:
                    for imp in v.improvements[:3]:
                        feedback_parts.append(f"[{r.variant_name}] {imp}")
                feedback = "\n".join(feedback_parts)

                # Store for evolution
                prev_specs = [r.spec for r in valid_results if r.spec]
                prev_results = valid_results
                prev_verdicts = critic_verdicts

                yield _text(
                    f"   Best so far: **{best_overall.variant_name if best_overall else '—'}** "
                    f"(Grade {best_overall.grade if best_overall else 'F'})\n"
                    f"   Refining strategies for next iteration...\n\n"
                )
            else:
                yield _text(
                    f"\n⚠️ Reached max iterations ({plan.max_iterations}). "
                    f"Finalizing best result.\n\n"
                )

        # ── Step 8: Finalize ────────────────────────────────────────────
        if best_overall is None:
            yield _text("❌ **No strategy produced results.** Check dataset quality.\n")
            return

        yield _text("🏁 **Step 8 — Finalizing Best Strategy**\n")
        yield _text(f"   Winner: **{best_overall.variant_name}** (Grade {best_overall.grade})\n")

        # Re-run with render=True
        yield _text("   📄 Generating report...\n")
        try:
            final = await self.backtester.run(
                best_overall.spec, dataset_id,
                init_cash=init_cash, render=True,
            )
            if final.report_url:
                yield _text(f"   Report: {final.report_url}\n")
            best_overall = final
        except Exception as exc:
            yield _text(f"   ⚠️ Report failed: {exc}\n")

        # Save to library
        yield _text("   💾 Saving to strategy library...\n")
        try:
            from ..tool_exec import run_tool
            save_result = await run_tool("save_strategy", {
                "name": best_overall.variant_name,
                "description": (
                    f"Auto-researched. Grade={best_overall.grade}, "
                    f"Sharpe={_fmt(best_overall.metrics.get('sharpe'))}, "
                    f"Trades={best_overall.metrics.get('num_trades', 0)}"
                ),
                "backtest_id": best_overall.backtest_id,
            })
            if save_result.get("ok"):
                sid = save_result["output"].get("strategy_id", "")
                yield _text(f"   ✅ Saved: {sid}\n")
        except Exception as exc:
            yield _text(f"   ⚠️ Save: {exc}\n")

        # Save to memory
        try:
            from ..memory import store as _mem_store
            _mem_store.save_strategy_result(
                best_overall.variant_name,
                best_overall.spec,
                best_overall.grade,
                best_overall.metrics,
                profile.regime if profile else "unknown",
            )
        except Exception:
            pass

        # ── Final Summary ───────────────────────────────────────────────
        elapsed = time.perf_counter() - t0
        yield _text(self._format_summary(best_overall, best_critic, all_results, elapsed, intent))

    def _format_summary(
        self,
        best: PipelineResult,
        critic: Optional[CriticVerdict],
        all_results: List[PipelineResult],
        elapsed: float,
        intent: ResearchIntent,
    ) -> str:
        m = best.metrics
        lines = [
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
            "## 🏆 Research Complete\n\n",
            f"**Strategy:** {best.variant_name}\n",
            f"**Grade:** {best.grade} | **Score:** {best.score:.1f}/100\n\n",
            "### Performance\n",
            "| Metric | Value |\n",
            "|--------|-------|\n",
            f"| Sharpe | {_fmt(m.get('sharpe'))} |\n",
            f"| Sortino | {_fmt(m.get('sortino'))} |\n",
            f"| Profit Factor | {_fmt(m.get('profit_factor'))} |\n",
            f"| Win Rate | {_pct(m.get('win_rate'))} |\n",
            f"| Max Drawdown | {_pct(m.get('max_drawdown'))} |\n",
            f"| Total Return | {_pct(m.get('total_return'))} |\n",
            f"| Trades | {m.get('num_trades', 0)} |\n",
        ]

        if best.wfe is not None:
            lines.append(f"| Walk-Forward Efficiency | {best.wfe:.2f} |\n")
        if best.mc_survival is not None:
            lines.append(f"| MC Survival Rate | {best.mc_survival:.1%} |\n")

        # Critic summary
        if critic:
            lines.append("\n### Quality Analysis\n")
            lines.append(f"| Check | Score |\n")
            lines.append(f"|-------|-------|\n")
            lines.append(f"| Overfitting | {1-critic.overfitting_score:.0%} clean |\n")
            lines.append(f"| Stability | {1-critic.instability_score:.0%} stable |\n")
            lines.append(f"| Risk Control | {critic.risk_control_score:.0%} |\n")
            lines.append(f"| Structure | {critic.structural_score:.0%} |\n")

        if best.vetos:
            lines.append("\n### Remaining Vetos\n")
            for v in best.vetos:
                lines.append(f"- ⚠️ **{v.get('rule', '?')}**: {v.get('message', '?')}\n")

        if best.report_url:
            lines.append(f"\n📄 **Report:** {best.report_url}\n")

        lines.append(
            f"\n*Tested {len(all_results)} variants in {elapsed:.1f}s*\n"
        )
        return "".join(lines)


# ─── Helpers ────────────────────────────────────────────────────────────

def _text(delta: str) -> Dict[str, Any]:
    return {"type": "text", "delta": delta}

def _fmt(v: Any) -> str:
    if v is None: return "—"
    try: return f"{float(v):.3f}"
    except (TypeError, ValueError): return "—"

def _pct(v: Any) -> str:
    if v is None: return "—"
    try: return f"{float(v)*100:.2f}%"
    except (TypeError, ValueError): return "—"
