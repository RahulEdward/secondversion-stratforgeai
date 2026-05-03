"""Library Skill — save, load, and list trading strategies."""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import BaseSkill


class Skill(BaseSkill):

    @property
    def name(self) -> str:
        return "library"

    @property
    def description(self) -> str:
        return (
            "Manage the strategy library: save strategies with grade/verdict, "
            "load a saved strategy by ID, and list all saved strategies."
        )

    def tools(self) -> List[Dict[str, Any]]:
        from ...tools import _library_tool_schemas
        return _library_tool_schemas()

    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kw: Any
    ) -> Dict[str, Any]:
        from ...tool_exec import _run_library_tool
        return await _run_library_tool(tool_name, input_)
