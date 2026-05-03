"""Indicator Skill — compute 65+ technical indicators on OHLCV data."""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import BaseSkill


class Skill(BaseSkill):

    @property
    def name(self) -> str:
        return "indicators"

    @property
    def description(self) -> str:
        return (
            "Compute 65+ technical indicators (RSI, MACD, Bollinger, "
            "SuperTrend, ADX, ATR, EMA, SMA, Stochastic, VWAP, Ichimoku, "
            "etc.) on any uploaded OHLCV dataset."
        )

    def tools(self) -> List[Dict[str, Any]]:
        from ...tools import indicator_tools
        return indicator_tools()

    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kw: Any
    ) -> Dict[str, Any]:
        from ...tool_exec import _run_indicator

        prefix = "compute_"
        if not tool_name.startswith(prefix):
            return {"ok": False, "error": f"Not an indicator tool: {tool_name}"}
        indicator_name = tool_name[len(prefix):]
        return await _run_indicator(indicator_name, input_)
