import { useEffect, useMemo, useRef, useState } from 'react';
import {
  FileText,
  Download,
  X,
  ExternalLink,
  Loader2,
  RefreshCw,
  ChevronDown,
} from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import { cn } from '@/lib/cn';
import PreviewPanel from './panels/PreviewPanel';
import FilesPanel from './panels/FilesPanel';
import TasksPanel from './panels/TasksPanel';
import DiffPanel from './panels/DiffPanel';
import TerminalPanel from './panels/TerminalPanel';
import RuntimePanel from './panels/RuntimePanel';
import ResizeHandle from './ResizeHandle';

// Pick the same backend base URL the API client uses. Repeated here so we
// don't drag in a circular dep from src/lib/api.ts; it's a 4-line constant.
const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BACKEND_BASE_URL = WEB_ONLY
  ? ''
  : ENV_URL && ENV_URL.length > 0
    ? ENV_URL
    : 'http://127.0.0.1:8765';

export default function ArtifactsPane() {
  const close = useAppStore((s) => s.toggleArtifacts);
  const reportId = useAppStore((s) => s.activeReportId);
  const reportTitle = useAppStore((s) => s.activeReportTitle);
  const setActiveReport = useAppStore((s) => s.setActiveReport);
  const mode = useAppStore((s) => s.rightPaneMode);
  const setMode = useAppStore((s) => s.setRightPaneMode);

  // Right-pane mode (Claude Code-style menu) wins over the default
  // report iframe — the user explicitly picked it from the dropdown.
  if (mode === 'preview') return <PaneWrap title="Preview" onClose={() => setMode(null)}><PreviewPanel /></PaneWrap>;
  if (mode === 'files')   return <PaneWrap title="Files"   onClose={() => setMode(null)}><FilesPanel /></PaneWrap>;
  if (mode === 'tasks')   return <PaneWrap title="Tasks"   onClose={() => setMode(null)}><TasksPanel /></PaneWrap>;
  if (mode === 'diff')    return <PaneWrap title="Diff"    onClose={() => setMode(null)}><DiffPanel /></PaneWrap>;
  if (mode === 'terminal')return <PaneWrap title="Terminal"onClose={() => setMode(null)}><TerminalPanel /></PaneWrap>;
  if (mode === 'runtime') return <PaneWrap title="Runtime" onClose={() => setMode(null)}><RuntimePanel /></PaneWrap>;

  // (Default below = legacy report iframe behaviour, preserved.)
  // Force-refresh the iframe by bumping a key. Useful after re-rendering a
  // report with the same id (the URL doesn't change but the file did).
  const [refreshTick, setRefreshTick] = useState(0);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [htmlBusy, setHtmlBusy] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const downloadWrapRef = useRef<HTMLDivElement | null>(null);

  // Close the download menu on any click that lands outside it. Keeps the
  // dropdown feeling native — Esc also closes (handled below).
  useEffect(() => {
    if (!downloadMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!downloadWrapRef.current) return;
      if (!downloadWrapRef.current.contains(e.target as Node)) {
        setDownloadMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDownloadMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [downloadMenuOpen]);

  const htmlUrl = useMemo(
    () => (reportId ? `${BACKEND_BASE_URL}/api/reports/${reportId}` : null),
    [reportId],
  );
  const pdfUrl = useMemo(
    () => (reportId ? `${BACKEND_BASE_URL}/api/reports/${reportId}.pdf` : null),
    [reportId],
  );

  /**
   * Generic blob-download helper. We fetch the asset ourselves (rather
   * than `<a download href=…>`) so the click reliably triggers a save
   * dialog inside Electron — letting the browser navigate to a
   * `text/html` URL with `download` would *render* it in a new tab on
   * some platforms, which is exactly the "blank page" the user saw.
   */
  const downloadBlob = async (
    url: string,
    filename: string,
    setBusy: (b: boolean) => void,
  ) => {
    setBusy(true);
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objUrl);
    } catch {
      // Last-resort fallback — let the OS handle it. Used to be the
      // primary path for the (broken) "blank page" case.
      window.open(url, '_blank');
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!pdfUrl || pdfBusy) return;
    setDownloadMenuOpen(false);
    // First request server-renders the PDF (Playwright) — a few seconds.
    await downloadBlob(pdfUrl, `${reportId}.pdf`, setPdfBusy);
  };

  const handleDownloadHtml = async () => {
    if (!htmlUrl || htmlBusy) return;
    setDownloadMenuOpen(false);
    await downloadBlob(htmlUrl, `${reportId}.html`, setHtmlBusy);
  };

  const downloadBusy = pdfBusy || htmlBusy;

  const handleOpenExternal = () => {
    if (htmlUrl) window.open(htmlUrl, '_blank');
  };

  const headerLabel = reportTitle || (reportId ? `Report ${reportId}` : 'Artifacts');
  const width = useAppStore((s) => s.artifactsWidth);
  const setWidth = useAppStore((s) => s.setArtifactsWidth);

  return (
    <aside
      style={{ width: `${width}px` }}
      className="relative flex flex-col shrink-0 bg-bg-sidebar border-l border-border-subtle"
    >
      <ResizeHandle side="left" width={width} onResize={setWidth} min={320} max={900} />
      <header className="h-11 flex items-center px-4 justify-between shrink-0 border-b border-border-subtle">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={14} className="text-fg-muted shrink-0" strokeWidth={1.75} />
          <span className="font-medium text-sm truncate">{headerLabel}</span>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          {reportId && (
            <>
              <button
                onClick={() => setRefreshTick((t) => t + 1)}
                className="p-1.5 rounded hover:bg-bg-hover text-fg-muted transition-colors"
                title="Reload"
              >
                <RefreshCw size={13} strokeWidth={1.75} />
              </button>
              <button
                onClick={handleOpenExternal}
                className="p-1.5 rounded hover:bg-bg-hover text-fg-muted transition-colors"
                title="Open in browser"
              >
                <ExternalLink size={13} strokeWidth={1.75} />
              </button>
              <div ref={downloadWrapRef} className="relative">
                <button
                  onClick={() => setDownloadMenuOpen((v) => !v)}
                  disabled={downloadBusy}
                  className={cn(
                    'flex items-center gap-0.5 p-1.5 rounded',
                    'hover:bg-bg-hover text-fg-muted transition-colors',
                    downloadBusy && 'opacity-60 cursor-wait',
                  )}
                  title="Download report"
                  aria-haspopup="menu"
                  aria-expanded={downloadMenuOpen}
                >
                  {downloadBusy ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Download size={13} strokeWidth={1.75} />
                  )}
                  <ChevronDown size={10} strokeWidth={2} />
                </button>
                {downloadMenuOpen && (
                  <div
                    role="menu"
                    className={cn(
                      'absolute right-0 top-full mt-1 z-20',
                      'min-w-[180px] py-1 rounded-md',
                      'bg-bg-panel border border-border shadow-lg',
                    )}
                  >
                    <DownloadMenuItem
                      label="Download as PDF"
                      hint="renders on first request"
                      busy={pdfBusy}
                      onClick={handleDownloadPdf}
                    />
                    <DownloadMenuItem
                      label="Download as HTML"
                      hint="single-file, charts inline"
                      busy={htmlBusy}
                      onClick={handleDownloadHtml}
                    />
                  </div>
                )}
              </div>
              <button
                onClick={() => setActiveReport(null)}
                className="p-1.5 rounded hover:bg-bg-hover text-fg-muted transition-colors"
                title="Close report"
              >
                <X size={13} strokeWidth={1.75} />
              </button>
            </>
          )}
          {!reportId && (
            <button
              onClick={close}
              className="p-1.5 rounded hover:bg-bg-hover text-fg-muted transition-colors"
              title="Close panel"
            >
              <X size={14} strokeWidth={1.75} />
            </button>
          )}
        </div>
      </header>

      {/* Body */}
      {htmlUrl ? (
        <div className="flex-1 min-h-0 bg-white">
          <iframe
            key={`${reportId}-${refreshTick}`}
            src={htmlUrl}
            title={reportTitle || `report ${reportId}`}
            sandbox="allow-scripts allow-same-origin allow-popups"
            className="w-full h-full border-0"
          />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-bg-hover flex items-center justify-center mx-auto">
              <FileText size={20} className="text-fg-subtle" strokeWidth={1.5} />
            </div>
            <p className="text-fg-muted text-sm">No artifact yet</p>
            <p className="text-xs text-fg-subtle max-w-[240px] mx-auto leading-relaxed">
              Run <span className="font-mono text-fg-muted">render_report</span> in
              chat to view backtest results, equity curves, walk-forward, and
              Monte Carlo charts here.
            </p>
          </div>
        </div>
      )}
    </aside>
  );
}


/**
 * One row of the download dropdown — label on the left, status / hint
 * on the right. Mirrors the lightweight Claude Code menu styling we use
 * elsewhere in the app rather than introducing a heavier popover lib.
 */
function DownloadMenuItem({
  label,
  hint,
  busy,
  onClick,
}: {
  label: string;
  hint?: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      disabled={busy}
      className={cn(
        'w-full flex items-center justify-between gap-3 px-3 py-1.5',
        'text-left text-sm text-fg hover:bg-bg-hover transition-colors',
        'disabled:opacity-60 disabled:cursor-wait',
      )}
    >
      <span>{label}</span>
      <span className="flex items-center gap-1.5 text-fg-subtle text-[11px]">
        {busy ? <Loader2 size={11} className="animate-spin" /> : null}
        {hint && !busy ? hint : null}
      </span>
    </button>
  );
}


/** Shared shell for non-report panes (Preview / Files / Tasks / etc.). */
function PaneWrap({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const width = useAppStore((s) => s.artifactsWidth);
  const setWidth = useAppStore((s) => s.setArtifactsWidth);
  return (
    <aside
      style={{ width: `${width}px` }}
      className="relative flex flex-col shrink-0 bg-bg-sidebar border-l border-border-subtle"
    >
      <ResizeHandle side="left" width={width} onResize={setWidth} min={320} max={900} />
      <header className="h-11 flex items-center px-4 justify-between shrink-0 border-b border-border-subtle">
        <span className="font-medium text-sm">{title}</span>
        <button
          onClick={onClose}
          className="p-1.5 rounded hover:bg-bg-hover text-fg-muted transition-colors"
          title="Close panel"
        >
          <X size={13} strokeWidth={1.75} />
        </button>
      </header>
      {children}
    </aside>
  );
}
