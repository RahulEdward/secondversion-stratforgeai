"""Preflight checks — stubbed for StratForge integration.

The original Vibe-Trading preflight probed LangChain provider env vars and
wrote ``.env`` templates. Under StratForge integration, LLM credentials live
in the OS keyring (via ``backend/app/secrets.py``) and the Settings UI, so
this module is intentionally inert — it returns "ready" for any caller that
still references it (``cli.py``, ``ui_services.py``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CheckResult:
    name: str
    status: str  # "ready" | "warning" | "error"
    message: str = ""
    critical: bool = False


def run_preflight(console: Optional[object] = None) -> List[CheckResult]:
    """Return a list of preflight check results.

    Always returns a single "ready" entry under StratForge — the React UI
    handles provider setup interactively in Settings → Providers.
    """
    return [CheckResult(name="llm_provider", status="ready", message="managed by StratForge")]
