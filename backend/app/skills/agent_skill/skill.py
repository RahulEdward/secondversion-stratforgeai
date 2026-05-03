"""Agent Skill — system tools (shell, file I/O, Python execution)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..base import BaseSkill


class Skill(BaseSkill):

    @property
    def name(self) -> str:
        return "agent_tools"

    @property
    def description(self) -> str:
        return (
            "System-level agent tools: shell command execution, file read/write, "
            "directory listing, and Python code execution. Permission-gated."
        )

    @property
    def timeout(self) -> float:
        return 60.0

    def tools(self) -> List[Dict[str, Any]]:
        from ...agent_tools import tool_schemas
        return tool_schemas()

    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kw: Any
    ) -> Dict[str, Any]:
        from ...agent_tools import AGENT_TOOLS, run_agent_tool

        if tool_name not in AGENT_TOOLS:
            return {"ok": False, "error": f"Unknown agent tool: {tool_name}"}

        permission_mode = kw.get("permission_mode", "accept-edits")
        return await run_agent_tool(tool_name, input_, permission_mode=permission_mode)
