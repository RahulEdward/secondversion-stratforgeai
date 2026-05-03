"""Backtest Skill — run backtests and the full validation pipeline."""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import BaseSkill


class Skill(BaseSkill):

    @property
    def name(self) -> str:
        return "backtesting"

    @property
    def description(self) -> str:
        return (
            "Run single backtests on trading strategies against OHLCV data, "
            "and execute the full pipeline (backtest → optimize → walk-forward "
            "→ Monte Carlo → score → report) in one call."
        )

    @property
    def timeout(self) -> float:
        return 300.0  # pipelines can take several minutes

    def tools(self) -> List[Dict[str, Any]]:
        from ...tools import _backtest_tool_schemas, _pipeline_tool_schemas
        return _backtest_tool_schemas() + _pipeline_tool_schemas()

    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kw: Any
    ) -> Dict[str, Any]:
        from ...tool_exec import _run_backtest_tool, _run_full_pipeline

        if tool_name == "run_full_pipeline":
            return await _run_full_pipeline(input_)

        backtest_tools = {
            "run_backtest", "optimize_strategy",
            "walk_forward", "monte_carlo", "score_strategy",
        }
        if tool_name in backtest_tools:
            return await _run_backtest_tool(tool_name, input_)

        return {"ok": False, "error": f"Unknown backtest tool: {tool_name}"}
