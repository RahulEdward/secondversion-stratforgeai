import { useEffect, useState } from 'react';
import { FileText, Download, ExternalLink, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';

// Backend base (same logic the API client uses)
const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BACKEND = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

interface ReportMeta {
  report_id: string;
  project_id: string;
  project_name: string;
  title: string;
  grade: string;
  verdict: string;
  score: number;
  created_at: string;
}

interface Props {
  reportId: string;
}

/**
 * Inline report summary card shown right inside an assistant turn.
 * Mimics Vibe-Trading's style: compact metric row + grade badge +
 * a primary "View Full Report" CTA that opens the full preview.
 *
 * Fetches the report's sidecar JSON (written alongside the HTML by
 * generate_report) so we can show grade/verdict/score without parsing
 * the chat text.
 */
export default function ReportCard({ reportId }: Props) {
  const [meta, setMeta] = useState<ReportMeta | null>(null);
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);
  const setActiveReport = useAppStore((s) => s.setActiveReport);
  const setPreviewUrl = useAppStore((s) => s.setPreviewUrl);

  // Fetch the sidecar JSON to get grade/verdict/score.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(`${BACKEND}/api/reports/${reportId}/meta`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (alive && data) setMeta(data as ReportMeta);
      })
      .catch(() => { /* ignore — we degrade gracefully */ })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [reportId]);

  // Separately, try to fetch quick metrics (if backend exposes them).
  useEffect(() => {
    let alive = true;
    fetch(`${BACKEND}/api/reports/${reportId}/metrics`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (alive && data && typeof data === 'object') {
          setMetrics(data as Record<string, number>);
        }
      })
      .catch(() => { /* ignore */ });
    return () => { alive = false; };
  }, [reportId]);

  const handleOpen = () => {
    setActiveReport(reportId, meta?.title ?? null);
    setPreviewUrl(`${BACKEND}/api/reports/${reportId}`);
  };

  const handlePdfDownload = () => {
    const pdfUrl = `${BACKEND}/api/reports/${reportId}.pdf`;
    const a = document.createElement('a');
    a.href = pdfUrl;
    a.download = `${reportId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleOpenExternal = () => {
    window.open(`${BACKEND}/api/reports/${reportId}`, '_blank');
  };

  const grade = meta?.grade ?? '—';
  const verdict = meta?.verdict ?? 'view';
  const score = meta?.score ?? 0;
  const title = meta?.title ?? 'Strategy Report';

  // Grade color mapping
  const gradeColor =
    grade.startsWith('A') ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' :
    grade.startsWith('B') ? 'bg-accent/15 text-accent border-accent/30' :
    grade.startsWith('C') ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
    grade === 'D'         ? 'bg-orange-500/15 text-orange-400 border-orange-500/30' :
    grade === 'F'         ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                            'bg-bg-hover text-fg-muted border-border';

  return (
    <div className="my-2 rounded-xl border border-border-subtle bg-bg-panel/60 overflow-hidden">
      {/* Header row */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle/60">
        <div className="w-8 h-8 rounded-lg bg-accent/15 border border-accent/25 flex items-center justify-center shrink-0">
          <FileText size={14} className="text-accent" strokeWidth={1.75} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-fg truncate">{title}</div>
          <div className="text-[11px] text-fg-subtle font-mono truncate">{reportId}</div>
        </div>
        <div className={cn(
          'shrink-0 px-2.5 py-1 rounded-md border text-xs font-mono font-bold tracking-wider',
          gradeColor,
        )}>
          {grade}
        </div>
      </div>

      {/* Metrics strip — only shown when we have data */}
      {metrics && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-0 border-b border-border-subtle/60">
          <Metric label="Sharpe"   value={metrics.sharpe}        fmt="n2" />
          <Metric label="Return"   value={metrics.total_return}  fmt="pct2" />
          <Metric label="Max DD"   value={metrics.max_drawdown}  fmt="pct2" kind="neg" />
          <Metric label="Trades"   value={metrics.trade_count}   fmt="int" />
          <Metric label="Win Rate" value={metrics.win_rate}      fmt="pct1" />
          <Metric label="PF"       value={metrics.profit_factor} fmt="n2" />
        </div>
      )}

      {/* Verdict + action row */}
      <div className="flex items-center gap-2 px-4 py-3">
        <div className="text-[11px] text-fg-muted flex-1">
          {loading ? (
            'Loading report…'
          ) : meta ? (
            <>
              Verdict: <span className="text-fg font-medium">{verdict}</span>
              {' · '}
              Score: <span className="text-fg font-mono">{score.toFixed(1)}</span>/100
            </>
          ) : (
            'Report metadata unavailable — full report still viewable.'
          )}
        </div>

        <button
          onClick={handlePdfDownload}
          title="Download PDF"
          className="p-1.5 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
        >
          <Download size={13} strokeWidth={1.75} />
        </button>
        <button
          onClick={handleOpenExternal}
          title="Open in browser"
          className="p-1.5 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
        >
          <ExternalLink size={13} strokeWidth={1.75} />
        </button>
        <button
          onClick={handleOpen}
          className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md bg-accent hover:bg-accent-hover text-white transition-colors"
        >
          <FileText size={12} strokeWidth={2} />
          View Full Report
        </button>
      </div>
    </div>
  );
}


// ── Compact metric cell ────────────────────────────────────────────────

type FmtKind = 'n2' | 'pct1' | 'pct2' | 'int';

function Metric({
  label,
  value,
  fmt,
  kind,
}: {
  label: string;
  value: number | undefined;
  fmt: FmtKind;
  kind?: 'neg';  // force-color negative/positive interpretation
}) {
  const display = formatMetric(value, fmt);
  const n = typeof value === 'number' && !Number.isNaN(value) ? value : null;

  let TrendIcon = Minus;
  let colorClass = 'text-fg';
  if (n !== null) {
    if (kind === 'neg') {
      // Max DD etc. — always visually "bad"
      TrendIcon = TrendingDown;
      colorClass = 'text-red-400';
    } else if (n > 0) {
      TrendIcon = TrendingUp;
      colorClass = 'text-emerald-400';
    } else if (n < 0) {
      TrendIcon = TrendingDown;
      colorClass = 'text-red-400';
    }
  }

  return (
    <div className="px-3 py-2.5 border-r border-border-subtle/40 last:border-r-0">
      <div className="text-[9px] text-fg-subtle uppercase tracking-wider mb-0.5">{label}</div>
      <div className={cn('text-sm font-mono tabular-nums flex items-center gap-1', colorClass)}>
        {display === '—' ? <Minus size={10} /> : <TrendIcon size={10} strokeWidth={2} />}
        <span>{display}</span>
      </div>
    </div>
  );
}

function formatMetric(v: number | undefined, fmt: FmtKind): string {
  if (v == null || Number.isNaN(v)) return '—';
  switch (fmt) {
    case 'n2':   return v.toFixed(2);
    case 'pct1': return `${(v * 100).toFixed(1)}%`;
    case 'pct2': return `${(v * 100).toFixed(2)}%`;
    case 'int':  return Math.round(v).toString();
  }
}
