"""Skill base contract — every skill must implement this interface.

A Skill is a self-contained capability: it owns its tool schemas AND
execution logic. Adding a new skill = drop a folder, no core changes.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Default per-skill execution timeout (seconds).
DEFAULT_TIMEOUT = 120.0


@dataclass
class SkillResult:
    """Standardised result from any skill execution."""

    ok: bool = True
    output: Any = None
    error: Optional[str] = None
    skill_name: str = ""
    tool_name: str = ""
    elapsed_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        if self.ok:
            return {"ok": True, "output": self.output}
        return {"ok": False, "error": self.error}


class BaseSkill(ABC):
    """Contract every skill must satisfy.

    Subclass this, set ``name`` and ``description``, implement
    ``tools()`` and ``execute()``, and drop the folder into
    ``backend/app/skills/``. The registry auto-discovers it.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique skill identifier (e.g. 'indicators', 'backtesting')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this skill does."""
        ...

    @property
    def timeout(self) -> float:
        """Max execution time in seconds. Override for heavy skills."""
        return DEFAULT_TIMEOUT

    @abstractmethod
    def tools(self) -> List[Dict[str, Any]]:
        """Return LLM-compatible tool schemas owned by this skill.

        Each schema follows the Anthropic/OpenAI tool format:
        ``{"name": "...", "description": "...", "input_schema": {...}}``
        """
        ...

    @abstractmethod
    async def execute(
        self, tool_name: str, input_: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        """Execute a tool call. Must return ``{"ok": True, "output": ...}``
        or ``{"ok": False, "error": "..."}``. Never raise — always catch."""
        ...

    def tool_names(self) -> List[str]:
        """Return all tool names this skill handles."""
        return [t["name"] for t in self.tools()]
