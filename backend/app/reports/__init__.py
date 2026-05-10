"""Reports — lookup + PDF helpers for rendered backtest reports.

The actual HTML/PDF generation lives in
``app.shadow_account.strategy_reporter.render_strategy_report`` (called
by the agent tool ``generate_report``). This package keeps only the
disk-level helpers the ``/api/reports/*`` routes use.
"""

from .render import (
    ReportMetadata,
    find_report,
    load_report_metadata,
    report_paths,
    render_report,  # kept as a stub that raises NotImplementedError
)
from .pdf import (
    ReportNotFound,
    export_pdf,
    export_pdf_sync,
    pdf_exists,
)

__all__ = [
    "ReportMetadata",
    "ReportNotFound",
    "export_pdf",
    "export_pdf_sync",
    "find_report",
    "load_report_metadata",
    "pdf_exists",
    "report_paths",
    "render_report",
]
