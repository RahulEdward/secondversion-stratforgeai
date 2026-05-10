"""PDF helpers for rendered reports.

``generate_report`` (agent tool) already writes the PDF alongside the HTML
via WeasyPrint at render time, so this module's main job is:

  1. Tell callers whether a cached PDF exists.
  2. Serve that cached PDF via ``export_pdf_sync``.
  3. If (somehow) the PDF is missing but the HTML exists, re-render it
     on-demand through WeasyPrint — no Playwright / Chromium dependency.
"""

from __future__ import annotations

from pathlib import Path

from .render import report_paths


class ReportNotFound(Exception):
    """The HTML file for this report_id is missing."""


def pdf_cache_path(project_id: str, report_id: str) -> Path:
    """Where the PDF *would* be, regardless of whether it's been rendered."""
    return report_paths(project_id, report_id)["pdf"]


def pdf_exists(project_id: str, report_id: str) -> bool:
    return pdf_cache_path(project_id, report_id).exists()


def export_pdf_sync(
    project_id: str,
    report_id: str,
    *,
    force: bool = False,
) -> Path:
    """Return the cached PDF path; re-render from HTML via WeasyPrint if missing.

    Raises:
        ReportNotFound: if the HTML file does not exist on disk.
    """
    paths = report_paths(project_id, report_id)
    html_path: Path = paths["html"]
    pdf_path: Path = paths["pdf"]

    if not html_path.exists():
        raise ReportNotFound(
            f"Report HTML missing for {report_id!r} under project {project_id!r}"
        )

    if pdf_path.exists() and not force:
        return pdf_path

    # Lazy fallback: convert HTML → PDF via WeasyPrint. If the package is
    # unavailable on this machine (Windows without GTK), we surface a
    # clear message instead of a 500.
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise ReportNotFound(
            f"PDF unavailable: weasyprint not installed ({exc})."
        )

    html_text = html_path.read_text(encoding="utf-8")
    HTML(string=html_text, base_url=str(html_path.parent)).write_pdf(str(pdf_path))
    return pdf_path


# Legacy async entry point kept as a thin wrapper so older imports don't break.
async def export_pdf(
    project_id: str,
    report_id: str,
    *,
    force: bool = False,
    timeout_ms: int = 20_000,  # noqa: ARG001 — kept for API compatibility
) -> Path:
    """Async wrapper around :func:`export_pdf_sync` (WeasyPrint is sync)."""
    import asyncio

    return await asyncio.to_thread(export_pdf_sync, project_id, report_id, force=force)
