import { useEffect, useState } from 'react';
import { X, Database } from 'lucide-react';
import { getDatasetPreview, type DatasetPreview } from '@/lib/api';

interface Props {
  datasetId: string;
  onClose: () => void;
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') {
    // Tight numeric formatting for OHLCV — max 4 sig figs after the decimal.
    if (Number.isInteger(v)) return v.toString();
    return v.toFixed(4).replace(/\.?0+$/, '');
  }
  return String(v);
}

export default function DatasetPreviewModal({ datasetId, onClose }: Props) {
  const [data, setData] = useState<DatasetPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDatasetPreview(datasetId, 50)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-[min(900px,92vw)] max-h-[82vh] bg-bg-panel border border-border rounded-xl shadow-popup flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <div className="flex items-center gap-2 min-w-0">
            <Database size={14} className="text-accent shrink-0" />
            <span className="font-medium truncate">
              {data?.filename ?? 'Loading…'}
            </span>
            {data && (
              <span className="text-xs text-fg-subtle shrink-0">
                · {data.rows.toLocaleString()} rows · {data.columns.length} cols
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-bg-hover text-fg-muted transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-auto">
          {error ? (
            <div className="p-6 text-sm text-red-400">{error}</div>
          ) : !data ? (
            <div className="p-6 text-sm text-fg-subtle italic">Loading preview…</div>
          ) : (
            <table className="w-full text-xs font-mono">
              <thead className="sticky top-0 bg-bg-panel border-b border-border-subtle">
                <tr>
                  <th className="px-3 py-2 text-left text-2xs font-medium text-fg-subtle uppercase tracking-wider w-10">
                    #
                  </th>
                  {data.columns.map((c) => (
                    <th
                      key={c}
                      className="px-3 py-2 text-left text-2xs font-medium text-fg-subtle uppercase tracking-wider whitespace-nowrap"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.sample.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-border-subtle hover:bg-bg-hover"
                  >
                    <td className="px-3 py-1.5 text-fg-faint tabular-nums">
                      {i + 1}
                    </td>
                    {data.columns.map((c) => (
                      <td
                        key={c}
                        className="px-3 py-1.5 text-fg whitespace-nowrap"
                      >
                        {formatCell(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="px-4 py-2 border-t border-border-subtle text-2xs text-fg-subtle">
          Showing first {data?.sample.length ?? 0} rows
        </div>
      </div>
    </div>
  );
}
