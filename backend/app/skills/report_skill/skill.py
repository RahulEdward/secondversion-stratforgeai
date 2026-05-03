"""Report Skill — generate HTML+PDF strategy reports."""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import BaseSkill


class Skill(BaseSkill):

    @property
    def name(self) -> str:
        return "reporting"

    @property
    def description(self) -> str:
        return (
            "Render comprehensive HTML+PDF strategy reports with equity curves, "
            "drawdown charts, trade distributions, walk-forward folds, "
            "Monte Carlo percentile bands, and composite scoring verdict."
        )

    def tools(self) -> List[Dict[str, Any]]:
        from ...tools import _report_tool_schemas
        return _report_tool_schemas()

    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kw: Any
    ) -> Dict[str, Any]:
        from ...tool_exec import _run_report_tool
        return await _run_report_tool(tool_name, input_)
