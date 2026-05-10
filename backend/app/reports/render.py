"""Report lookup helpers.

The heavy HTML rendering lives in ``app.shadow_account.strategy_reporter``
(Vibe-Trading-style reporter). This module keeps only the file-path
helpers that the ``/api/reports/*`` routes use to locate rendered HTML,
PDF, and sidecar JSON on disk.

Reports are written to ``<workspaces>/<project_id>/reports/<report_id>.{html,pdf,json}``
by ``generate_report`` (see ``app.agent_tools.report_tool``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..paths import workspace_dir


def _reports_dir(project_id: str) -> Path:
    p = workspace_dir(project_id) / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def report_paths(project_id: str, report_id: str) -> Dict[str, Path]:
    """Return the canonical file locations for a report (json/html/pdf)."""
    d = _reports_dir(project_id)
    return {
        "json": d / f"{report_id}.json",
        "html": d / f"{report_id}.html",
        "pdf": d / f"{report_id}.pdf",
    }


def load_report_metadata(project_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    """Load the sidecar JSON metadata for a report, or None if missing."""
    path = report_paths(project_id, report_id)["json"]
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def find_report(report_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Scan all workspaces for the report id — returns (project_id, metadata)."""
    from .. import paths as _paths

    for ws in _paths.WORKSPACES_DIR.iterdir():
        if not ws.is_dir():
            continue
        cand = ws / "reports" / f"{report_id}.json"
        if cand.exists():
            try:
                return ws.name, json.loads(cand.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return None


@dataclass
class ReportMetadata:
    """Back-compat shape retained so older scripts don't break."""

    report_id: str
    project_id: str
    project_name: str
    backtest_id: str
    title: str = ""
    grade: str = "C"
    verdict: str = "view"
    score: float = 0.0
    created_at: str = ""
    sections: list = field(default_factory=list)
    monte_carlo_id: Optional[str] = None
    walk_forward_id: Optional[str] = None
    optimization_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "backtest_id": self.backtest_id,
            "title": self.title,
            "grade": self.grade,
            "verdict": self.verdict,
            "score": self.score,
            "created_at": self.created_at,
            "sections": list(self.sections),
            "monte_carlo_id": self.monte_carlo_id,
            "walk_forward_id": self.walk_forward_id,
            "optimization_id": self.optimization_id,
        }


def render_report(*_args, **_kwargs):  # noqa: D401
    """Deprecated — use ``generate_report`` agent tool (see app.agent_tools.report_tool).

    Old callers of ``render_report(backtest_id=...)`` relied on StratForge's
    pre-Vibe-Trading persistence layer (``bt_xxxx`` IDs with sidecar JSONs).
    That layer has been replaced by the Vibe-Trading backtest engine +
    strategy_reporter. Kept as a stub so scripts that import the name
    still fail loudly instead of silently.
    """
    raise NotImplementedError(
        "render_report() has been replaced. "
        "Use app.shadow_account.strategy_reporter.render_strategy_report(run_dir=...) "
        "or the agent tool `generate_report`."
    )
