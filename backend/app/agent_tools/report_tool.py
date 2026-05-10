"""Report tool — produce a Vibe-Trading-style HTML + PDF report for a
finished backtest.

Delegates to app.shadow_account.strategy_reporter which renders the exact
same dark glassy layout as Vibe-Trading's Shadow Account report, but fed
with StratForge's backtest artifacts (metrics.csv / equity.csv / trades.csv).

The report is saved under the active project's workspaces/<pid>/reports/
directory and is served over the existing /api/reports/{report_id} route,
so the UI's Preview panel auto-opens it without any extra wiring.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.tools import BaseTool
from app.agent_tools.path_utils import safe_run_dir

logger = logging.getLogger(__name__)


def generate_report_fn(
    run_dir: str,
    strategy_name: str = "",
    takeaway: str = "",
    project_id: str | None = None,
) -> str:
    """Render a full HTML + PDF report for a backtest run_dir.

    Returns JSON with report_id + preview_url + pdf_url. The UI listens for
    these and auto-opens the Preview panel.
    """
    try:
        run_path = safe_run_dir(run_dir)
    except ValueError as exc:
        return json.dumps({"status": "error", "error": str(exc)})

    metrics_csv = run_path / "artifacts" / "metrics.csv"
    if not metrics_csv.exists():
        return json.dumps({
            "status": "error",
            "error": "No artifacts/metrics.csv — run backtest first.",
        })

    # Resolve a project_id so the report lives in the right workspace.
    try:
        from app import storage
        from app.paths import workspace_dir

        if project_id:
            project = storage.get_project(project_id)
            if project is None:
                project_id = None

        if project_id is None:
            projects = storage.list_projects()
            project_id = projects[0].id if projects else None

        if project_id is None:
            return json.dumps({
                "status": "error",
                "error": "No project available to store the report.",
            })

        reports_dir = workspace_dir(project_id) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.exception("Project/workspace lookup failed")
        return json.dumps({"status": "error", "error": f"Workspace lookup failed: {exc}"})

    # Pull dataset + config hints for the cover block.
    dataset_id = ""
    interval = ""
    initial_cash = 1_000_000.0
    date_range = ("", "")
    try:
        cfg_path = run_path / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(cfg.get("codes"), list) and cfg["codes"]:
                dataset_id = str(cfg["codes"][0])
            interval = str(cfg.get("interval", "") or "")
            initial_cash = float(cfg.get("initial_cash", 1_000_000) or 1_000_000)
            date_range = (
                str(cfg.get("start_date", "") or ""),
                str(cfg.get("end_date", "") or ""),
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        from app.shadow_account.strategy_reporter import render_strategy_report

        rendered = render_strategy_report(
            run_dir=run_path,
            strategy_name=strategy_name or f"Backtest {run_path.name}",
            output_dir=reports_dir,
            takeaway=takeaway or "",
            dataset_id=dataset_id,
            interval=interval,
            date_range=date_range,
            initial_cash=initial_cash,
        )
    except Exception as exc:
        logger.exception("Report generation failed")
        return json.dumps({"status": "error", "error": f"Report render failed: {exc}"})

    report_id = rendered["report_id"]

    # Persist a minimal JSON sidecar so the existing /api/reports route
    # (which keys off workspace_dir(pid)/reports/<id>.json) can serve the HTML.
    sidecar = {
        "report_id": report_id,
        "project_id": project_id,
        "project_name": project_id,
        "backtest_id": run_path.name,
        "title": strategy_name or f"Backtest {run_path.name}",
        "grade": rendered.get("grade", "C"),
        "verdict": rendered.get("verdict", "iterate"),
        "score": float(rendered.get("score", 0.0)),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sections": [
            "cover", "metrics", "equity", "drawdown",
            "trades_distribution", "trades_tail", "caveats",
        ],
    }
    try:
        (reports_dir / f"{report_id}.json").write_text(
            json.dumps(sidecar, indent=2), encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write sidecar json: %s", exc)

    preview_url = f"http://127.0.0.1:8765/api/reports/{report_id}"
    pdf_url = f"http://127.0.0.1:8765/api/reports/{report_id}.pdf"

    return json.dumps({
        "status": "ok",
        "report_id": report_id,
        "title": sidecar["title"],
        "grade": rendered.get("grade"),
        "verdict": rendered.get("verdict"),
        "score": rendered.get("score"),
        "preview_url": preview_url,
        "pdf_url": pdf_url,
        "pdf_engine": rendered.get("engine", "html-only"),
        "action": "open_preview",
        "url": preview_url,
        "message": (
            f"Report {report_id} generated. It will open automatically in the "
            f"Preview panel; PDF is available at {pdf_url}."
        ),
    })


class GenerateReportTool(BaseTool):
    name = "generate_report"
    description = (
        "Render a polished HTML + PDF report for a finished backtest. "
        "Reads artifacts/metrics.csv, equity.csv, and trades.csv from the "
        "given run_dir and produces equity curve + drawdown + trade "
        "distribution charts with a dark purple theme. The UI auto-opens "
        "the report in the Preview panel. PDF is available at the same URL "
        "with .pdf appended. MUST be called after every backtest."
    )
    parameters = {
        "type": "object",
        "properties": {
            "run_dir": {
                "type": "string",
                "description": "Backtest run directory (same value you passed to the backtest tool).",
            },
            "strategy_name": {
                "type": "string",
                "description": "Human-readable strategy label for the report cover.",
            },
            "takeaway": {
                "type": "string",
                "description": "Optional 1-2 sentence commentary for the cover block.",
            },
        },
        "required": ["run_dir"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs) -> str:
        return generate_report_fn(
            run_dir=kwargs["run_dir"],
            strategy_name=kwargs.get("strategy_name", "") or "",
            takeaway=kwargs.get("takeaway", "") or "",
        )
