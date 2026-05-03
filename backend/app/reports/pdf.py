"""PDF export for rendered reports (Phase 8, Slice 4).

Loads the pre-rendered `rp_<id>.html` in a headless Chromium tab, waits for
`window.__reportReady === true` (set by the template once every Plotly
figure has finished), and prints to A4. The resulting PDF is cached next
to the HTML; subsequent calls short-circuit unless `force=True`.

We use the **async** Playwright API because FastAPI request handlers are
coroutines — `sync_playwright` would deadlock the event loop. For the CLI
smoke path we provide `export_pdf_sync` which spins up a fresh loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright

from ..paths import workspace_dir
from .render import report_paths


# Default A4 with a touch of margin — matches the 1080px report width.
PDF_OPTIONS = {
    "format": "A4",
    "print_background": True,
    "margin": {"top": "12mm", "right": "10mm", "bottom": "14mm", "left": "10mm"},
    "prefer_css_page_size": False,
}


class ReportNotFound(Exception):
    """The HTML file for this report_id is missing."""


async def export_pdf(
    project_id: str,
    report_id: str,
    *,
    force: bool = False,
    timeout_ms: int = 20_000,
) -> Path:
    """Render `rp_<id>.pdf` for the given project/report. Returns the path.

    Raises:
        ReportNotFound: if the HTML file does not exist.
    """
    paths = report_paths(project_id, report_id)
    html_path: Path = paths["html"]
    pdf_path: Path = paths["pdf"]

    if not html_path.exists():
        raise ReportNotFound(
            f"Report HTML missing for {report_id!r} under project {project_id!r}"
        )

    if pdf_path.exists() and not force:
        # Already cached — no need to re-render.
        return pdf_path

    # Playwright needs a file:// URL on Windows, and it must be absolute.
    file_url = html_path.resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--disable-web-security"])
        try:
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 1600},
                device_scale_factor=2,
                # Accept local file access by default — no special flag needed.
            )
            page = await ctx.new_page()

            await page.goto(file_url, wait_until="networkidle", timeout=timeout_ms)

            # Wait for the template's readiness flag — set once every Plotly
            # figure has resolved. Falls back to the 8 s template fuse if the
            # CDN never loads.
            try:
                await page.wait_for_function(
                    "window.__reportReady === true",
                    timeout=timeout_ms,
                )
            except Exception:
                # Don't fail the PDF because the ready flag timed out — the
                # page is still paintable, just possibly without figures.
                pass

            # Settle pause so Plotly's final layout pass completes and paints to DOM.
            await page.wait_for_timeout(2000)

            await page.emulate_media(media="print")
            pdf_bytes = await page.pdf(**PDF_OPTIONS)
            pdf_path.write_bytes(pdf_bytes)
        finally:
            await browser.close()

    return pdf_path


def export_pdf_sync(
    project_id: str,
    report_id: str,
    *,
    force: bool = False,
    timeout_ms: int = 20_000,
) -> Path:
    """Blocking wrapper — runs a private event loop.

    On Windows we must run under a `ProactorEventLoop` because Playwright
    spawns Chromium via `asyncio.create_subprocess_exec`, which is
    unsupported by the `SelectorEventLoop` that uvicorn installs as the
    process-wide policy when reload watchers are active. Building a
    fresh Proactor loop here keeps uvicorn's Selector policy intact for
    the rest of the app.
    """
    import sys

    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        try:
            return loop.run_until_complete(
                export_pdf(
                    project_id, report_id, force=force, timeout_ms=timeout_ms
                )
            )
        finally:
            loop.close()
    return asyncio.run(
        export_pdf(project_id, report_id, force=force, timeout_ms=timeout_ms)
    )


def pdf_cache_path(project_id: str, report_id: str) -> Path:
    """Where the PDF *would* be, regardless of whether it's been rendered."""
    return report_paths(project_id, report_id)["pdf"]


def pdf_exists(project_id: str, report_id: str) -> bool:
    return pdf_cache_path(project_id, report_id).exists()
