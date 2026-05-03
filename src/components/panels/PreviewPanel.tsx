import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, RefreshCw, ExternalLink, Eye, Globe,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';

const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BACKEND = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

/** Common URLs the user might want to preview. Their own UI dev server
 *  comes first so "Preview" feels like Claude Code's preview pane out
 *  of the box. */
const PRESETS = [
  { label: 'StratForge UI', url: 'http://localhost:5173/' },
  { label: 'API docs',      url: 'http://127.0.0.1:8765/docs' },
];

export default function PreviewPanel() {
  const reportId = useAppStore((s) => s.activeReportId);
  const reportTitle = useAppStore((s) => s.activeReportTitle);

  // If there is an active report, the user almost certainly wants to see
  // that. Otherwise default to their own UI so the pane works like
  // Claude Code's preview out of the box.
  const initial = reportId
    ? `${BACKEND}/api/reports/${reportId}`
    : PRESETS[0].url;

  const [url, setUrl] = useState(initial);
  const [draft, setDraft] = useState(initial);
  const [tick, setTick] = useState(0);
  // Lightweight history so back/forward works without iframe hooks.
  const [history, setHistory] = useState<string[]>([initial]);
  const [hIdx, setHIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Switch to a freshly-rendered report when one arrives via a tool result.
  useEffect(() => {
    if (reportId) {
      const next = `${BACKEND}/api/reports/${reportId}`;
      setUrl(next);
      setDraft(next);
      setHistory((h) => [...h, next]);
      setHIdx((i) => i + 1);
    }
  }, [reportId]);

  const navigate = (next: string) => {
    if (!next || next === url) return;
    // Add http:// if user pasted a bare hostname.
    const normalised = /^https?:\/\//i.test(next) ? next : `http://${next}`;
    setUrl(normalised);
    setDraft(normalised);
    setHistory((h) => {
      const trimmed = h.slice(0, hIdx + 1);
      return [...trimmed, normalised];
    });
    setHIdx((i) => i + 1);
  };

  const goBack = () => {
    if (hIdx > 0) {
      const i = hIdx - 1;
      setHIdx(i);
      setUrl(history[i]);
      setDraft(history[i]);
    }
  };
  const goForward = () => {
    if (hIdx < history.length - 1) {
      const i = hIdx + 1;
      setHIdx(i);
      setUrl(history[i]);
      setDraft(history[i]);
    }
  };
  const reload = () => setTick((t) => t + 1);
  const openExternal = () => window.open(url, '_blank');

  const isReport = url.includes('/api/reports/');
  const headerLabel = isReport
    ? (reportTitle || `Report ${reportId ?? ''}`)
    : 'Preview';

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Browser-style chrome */}
      <div className="px-2 py-2 border-b border-border-subtle space-y-1.5">
        <div className="flex items-center gap-1.5">
          <button
            onClick={goBack}
            disabled={hIdx === 0}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover disabled:opacity-30 transition-colors"
            title="Back"
          >
            <ArrowLeft size={13} strokeWidth={1.75} />
          </button>
          <button
            onClick={goForward}
            disabled={hIdx >= history.length - 1}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover disabled:opacity-30 transition-colors"
            title="Forward"
          >
            <ArrowRight size={13} strokeWidth={1.75} />
          </button>
          <button
            onClick={reload}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
            title="Reload"
          >
            <RefreshCw size={13} strokeWidth={1.75} />
          </button>
          <div className="flex-1 min-w-0 relative">
            <Globe size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-fg-faint" />
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') navigate(draft.trim()); }}
              spellCheck={false}
              className={cn(
                'w-full h-7 pl-7 pr-2 rounded bg-bg border border-border',
                'text-[11px] font-mono text-fg placeholder:text-fg-faint',
                'focus:outline-none focus:border-border-strong',
              )}
            />
          </div>
          <button
            onClick={openExternal}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
            title="Open in browser"
          >
            <ExternalLink size={13} strokeWidth={1.75} />
          </button>
        </div>

        {/* Preset chips — quick targets */}
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-[10px] text-fg-subtle pr-1 inline-flex items-center gap-1">
            <Eye size={10} /> Preview:
          </span>
          {PRESETS.map((p) => (
            <button
              key={p.url}
              onClick={() => navigate(p.url)}
              className={cn(
                'h-5 px-1.5 rounded-full text-[10px] transition-colors',
                url.startsWith(p.url)
                  ? 'bg-bg-active text-fg'
                  : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
              )}
            >
              {p.label}
            </button>
          ))}
          {reportId && (
            <button
              onClick={() => navigate(`${BACKEND}/api/reports/${reportId}`)}
              className={cn(
                'h-5 px-1.5 rounded-full text-[10px] transition-colors',
                isReport ? 'bg-bg-active text-fg' : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
              )}
            >
              Report
            </button>
          )}
        </div>
      </div>

      {/* Iframe — bg-white so any transparent app shows correctly */}
      <div className="flex-1 min-h-0 bg-white">
        <iframe
          key={`${url}-${tick}`}
          src={url}
          title={headerLabel}
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-modals"
          className="w-full h-full border-0"
        />
      </div>
    </div>
  );
}
