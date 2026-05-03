"""Backtester agent — runs the full pipeline on a strategy spec.

No LLM needed: directly calls ``_do_run_full_pipeline`` from tool_exec
to execute backtest → optimize → walk-forward → Monte Carlo → score
in a single server-side pass.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from .base import PipelineResult


class Backtester:
    """Wraps ``run_full_pipeline`` and returns a compact PipelineResult."""

    async def run(
        self,
        spec: Dict[str, Any],
        dataset_id: str,
        *,
        optimize_grid: Optional[Dict[str, list]] = None,
        init_cash: float = 10_000.0,
        render: bool = False,
    ) -> PipelineResult:
        """Execute the full pipeline and return a PipelineResult."""
        return await asyncio.to_thread(
            self._run_sync, spec, dataset_id,
            optimize_grid=optimize_grid,
            init_cash=init_cash,
            render=render,
        )

    def _run_sync(
        self,
        spec: Dict[str, Any],
        dataset_id: str,
        *,
        optimize_grid: Optional[Dict[str, list]] = None,
        init_cash: float = 10_000.0,
        render: bool = False,
    ) -> PipelineResult:
        from ..tool_exec import run_tool
        import asyncio as _aio

        pipeline_input: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "strategy_spec": spec,
            "walk_forward": True,
            "wf_n_folds": 3,
            "wf_mode": "rolling",
            "wf_is_oos_split": 0.7,
            "monte_carlo": True,
            "mc_n_iterations": 1000,
            "mc_seed": 42,
            "render": render,
            "init_cash": init_cash,
        }

        if optimize_grid:
            pipeline_input["optimize"] = True
            pipeline_input["optimize_grid"] = optimize_grid

        # run_tool is async — run it in a new event loop for the sync context
        # Actually, we're already in a thread (called via asyncio.to_thread),
        # so we need to call the sync pipeline directly.
        from ..tool_exec import _do_run_full_pipeline
        result = _do_run_full_pipeline(pipeline_input)

        return self._parse_result(result, spec)

    def _parse_result(
        self, result: Dict[str, Any], spec: Dict[str, Any]
    ) -> PipelineResult:
        """Convert raw tool output to PipelineResult."""
        pr = PipelineResult()
        pr.spec = spec
        pr.variant_name = spec.get("name", "Unknown")

        if not result.get("ok"):
            pr.error = result.get("error", "Pipeline failed")
            return pr

        output = result.get("output", {})
        pr.backtest_id = output.get("backtest_id")
        pr.optimization_id = output.get("optimization_id")
        pr.elapsed_sec = output.get("elapsed_sec", 0)

        # Walk-forward
        wf = output.get("walk_forward") or {}
        pr.walk_forward_id = wf.get("walk_forward_id")
        pr.wfe = wf.get("wfe")

        # Monte Carlo
        mc = output.get("monte_carlo") or {}
        pr.monte_carlo_id = mc.get("monte_carlo_id")
        pr.mc_survival = mc.get("survival_rate")
        pr.mc_p_value = mc.get("p_value_positive_mean")

        # Score
        score = output.get("score") or {}
        pr.grade = score.get("grade", "F")
        pr.verdict = score.get("verdict", "reject")
        pr.score = score.get("score", 0.0)
        pr.vetos = score.get("vetos", [])

        # Metrics
        pr.metrics = output.get("metrics", {})

        # Report
        report = output.get("report") or {}
        if "html_url" in report:
            pr.report_url = report["html_url"]

        # Use the final optimized spec if available
        final_spec = output.get("final_spec_used")
        if isinstance(final_spec, dict):
            pr.spec = final_spec

        return pr
