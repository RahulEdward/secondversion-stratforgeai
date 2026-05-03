"""Reports — HTML + PDF output for a finished backtest.

Public entry points:
    render.render_report(backtest_id=..., monte_carlo_id=..., walk_forward_id=...,
                         optimization_id=...) -> ReportMetadata
    pdf.export_pdf(project_id, report_id, *, force=False) -> Path

The HTML is written eagerly on `render_report` so the viewer route can serve
it immediately; the PDF is rendered lazily on first request and cached.
"""

from .render import render_report, load_report_metadata, report_paths, find_report
from .pdf import export_pdf, export_pdf_sync, pdf_exists, ReportNotFound

__all__ = [
    "render_report",
    "load_report_metadata",
    "report_paths",
    "find_report",
    "export_pdf",
    "export_pdf_sync",
    "pdf_exists",
    "ReportNotFound",
]
