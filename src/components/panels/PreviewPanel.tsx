import { useEffect, useState } from 'react';
import { RefreshCw, ExternalLink, FileText } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';

const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BACKEND = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

/**
 * Preview panel — shows reports and agent-built apps only.
 * No URL bar, no presets, no self-referencing iframe.
 * Content loads automatically when:
 *   - Agent generates an HTML report (render_report tool)
 *   - Agent starts a dev server (start_process tool with detected port)
 *   - Agent sets a preview URL via open_preview tool
 */
export default function PreviewPanel() {
  const reportId = useAppStore((s) => s.activeReportId);
  const reportTitle = useAppStore((s) => s.activeReportTitle);
  const previewUrl = useAppStore((s) => s.previewUrl);

  // Determine what to show
  const url = previewUrl
    ? previewUrl
    : reportId
      ? `${BACKEND}/api/reports/${reportId}`
      : '';

  const [tick, setTick] = useState(0);

  const reload = () => setTick((t) => t + 1);
  const openExternal = () => { if (url) window.open(url, '_blank'); };

  const title = reportTitle || (reportId ? `Report ${reportId}` : 'Preview');

  // Empty state — nothing to show yet
  if (!url) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-bg-hover flex items-center justify-center mx-auto">
            <FileText size={20} className="text-fg-subtle" strokeWidth={1.5} />
          </div>
          <p className="text-fg-muted text-sm">No preview yet</p>
          <p className="text-xs text-fg-subtle max-w-[220px] mx-auto leading-relaxed">
            Run a strategy backtest or ask the agent to generate a report.
            It will appear here automatically.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Minimal header — just title + reload + external */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle">
        <span className="text-xs text-fg-muted truncate">{title}</span>
        <div className="flex items-center gap-1">
          <button
            onClick={reload}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
            title="Reload"
          >
            <RefreshCw size={12} strokeWidth={1.75} />
          </button>
          <button
            onClick={openExternal}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
            title="Open in browser"
          >
            <ExternalLink size={12} strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {/* Content iframe */}
      <div className="flex-1 min-h-0 bg-white">
        <iframe
          key={`${url}-${tick}`}
          src={url}
          title={title}
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          className="w-full h-full border-0"
        />
      </div>
    </div>
  );
}
