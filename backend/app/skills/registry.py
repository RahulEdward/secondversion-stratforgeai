"""Skill Registry — auto-discovery, routing, and execution.

Scans ``backend/app/skills/`` for folders containing a ``skill.py``
with a ``Skill`` class (subclass of :class:`BaseSkill`). Registers
each one and builds a tool_name → skill lookup table.

Usage::

    from app.skills import registry

    tools = registry.all_tools()          # for the LLM
    result = await registry.execute(name, input_)  # dispatch
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseSkill, DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

# ─── Global state ───────────────────────────────────────────────────────

_skills: Dict[str, BaseSkill] = {}          # skill_name → instance
_tool_map: Dict[str, BaseSkill] = {}        # tool_name → owning skill
_all_tools_cache: Optional[List[Dict[str, Any]]] = None
_initialized: bool = False


# ─── Discovery ──────────────────────────────────────────────────────────


def discover() -> None:
    """Scan the skills directory and register every valid skill.

    Safe to call multiple times — clears and rebuilds.
    """
    global _skills, _tool_map, _all_tools_cache, _initialized

    _skills.clear()
    _tool_map.clear()
    _all_tools_cache = None

    skills_dir = Path(__file__).parent
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        skill_py = child / "skill.py"
        if not skill_py.exists():
            continue

        module_path = f"app.skills.{child.name}.skill"
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            logger.warning("Failed to import skill %s: %s", child.name, exc)
            continue

        # Find the Skill class (first BaseSkill subclass in the module)
        skill_cls = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
            ):
                skill_cls = attr
                break

        if skill_cls is None:
            logger.warning("No BaseSkill subclass found in %s", module_path)
            continue

        try:
            instance = skill_cls()
            _register(instance)
            logger.info(
                "Registered skill: %s (%d tools)",
                instance.name,
                len(instance.tool_names()),
            )
        except Exception as exc:
            logger.warning("Failed to instantiate skill %s: %s", child.name, exc)


def _register(skill: BaseSkill) -> None:
    """Add a skill to the registry."""
    if skill.name in _skills:
        logger.warning("Duplicate skill name: %s — overwriting", skill.name)

    _skills[skill.name] = skill
    for tool_name in skill.tool_names():
        if tool_name in _tool_map:
            logger.warning(
                "Tool %s claimed by %s, already owned by %s — overwriting",
                tool_name,
                skill.name,
                _tool_map[tool_name].name,
            )
        _tool_map[tool_name] = skill


def register_skill(skill: BaseSkill) -> None:
    """Manually register a skill (e.g., from tests or plugins)."""
    _register(skill)
    global _all_tools_cache
    _all_tools_cache = None  # invalidate cache


# ─── Public API ─────────────────────────────────────────────────────────


def ensure_initialized() -> None:
    """Initialize if not yet done. Thread-safe via the GIL."""
    global _initialized
    if not _initialized:
        discover()
        _initialized = True


def all_tools() -> List[Dict[str, Any]]:
    """Return merged tool schemas from all registered skills."""
    global _all_tools_cache
    ensure_initialized()
    if _all_tools_cache is None:
        tools: List[Dict[str, Any]] = []
        for skill in _skills.values():
            try:
                tools.extend(skill.tools())
            except Exception as exc:
                logger.warning("Skill %s.tools() failed: %s", skill.name, exc)
        _all_tools_cache = tools
    return _all_tools_cache


def get_skill(name: str) -> Optional[BaseSkill]:
    """Look up a skill by name."""
    ensure_initialized()
    return _skills.get(name)


def get_skill_for_tool(tool_name: str) -> Optional[BaseSkill]:
    """Find which skill owns a tool."""
    ensure_initialized()
    return _tool_map.get(tool_name)


def list_skills() -> List[Dict[str, str]]:
    """Return a summary of all registered skills."""
    ensure_initialized()
    return [
        {
            "name": s.name,
            "description": s.description,
            "tools": s.tool_names(),
        }
        for s in _skills.values()
    ]


async def execute(
    tool_name: str,
    input_: Dict[str, Any],
    **kwargs: Any,
) -> Dict[str, Any]:
    """Route a tool call to its owning skill. Never raises."""
    ensure_initialized()

    skill = _tool_map.get(tool_name)
    if skill is None:
        return {"ok": False, "error": f"No skill owns tool: {tool_name}"}

    timeout = skill.timeout
    t0 = time.perf_counter()

    try:
        result = await asyncio.wait_for(
            skill.execute(tool_name, input_, **kwargs),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "error": (
                f"Skill '{skill.name}' timed out after {timeout:.0f}s "
                f"on tool '{tool_name}'"
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Skill '{skill.name}' crashed: {exc.__class__.__name__}: {exc}",
        }

    elapsed = time.perf_counter() - t0
    logger.debug(
        "Skill %s → %s completed in %.2fs",
        skill.name, tool_name, elapsed,
    )
    return result


# ─── Convenience ────────────────────────────────────────────────────────


def reload() -> None:
    """Force re-discovery (e.g. after dropping a new skill folder)."""
    global _initialized
    _initialized = False
    discover()
    _initialized = True
