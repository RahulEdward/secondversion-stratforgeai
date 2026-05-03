import { useState } from 'react';
import { GitCompare, RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/cn';

const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BASE = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

const PRESETS = [
  { label: 'Status', cmd: 'git status' },
  { label: 'Diff (working)', cmd: 'git diff' },
  { label: 'Diff (staged)', cmd: 'git diff --cached' },
  { label: 'Last commit', cmd: 'git log -1 -p' },
];

export default function DiffPanel() {
  const [cmd, setCmd] = useState(PRESETS[1].cmd);
  const [out, setOut] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (which: string) => {
    setCmd(which);
    setLoading(true);
    setError(null);
    setOut('');
    try {
      const resp = await fetch(`${BASE}/api/agent/tool`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'shell',
          input: { command: which },
          permission_mode: 'bypass',
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || 'shell failed');
      const o = data.output ?? {};
      const stdout = o.stdout || '';
      const stderr = o.stderr || '';
      setOut([stdout, stderr ? `\n[stderr]\n${stderr}` : ''].filter(Boolean).join(''));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-fg">
          <GitCompare size={14} className="text-accent" strokeWidth={1.75} />
          <span className="font-medium">Diff</span>
        </div>
        <button
          onClick={() => run(cmd)}
          disabled={loading}
          className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        </button>
      </div>

      <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-1 flex-wrap">
        {PRESETS.map((p) => (
          <button
            key={p.cmd}
            onClick={() => run(p.cmd)}
            className={cn(
              'h-6 px-2 rounded-full text-[11px] transition-colors',
              cmd === p.cmd ? 'bg-bg-active text-fg' : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto bg-bg p-3">
        {error && (
          <div className="text-xs text-amber-300 flex items-start gap-1.5 mb-2">
            <AlertCircle size={12} className="mt-0.5 shrink-0" /> {error}
          </div>
        )}
        {!error && !loading && !out && (
          <div className="text-[11px] text-fg-subtle">Click a preset above to run.</div>
        )}
        {out && (
          <pre className="text-[11.5px] font-mono whitespace-pre-wrap break-all text-fg-muted leading-relaxed">
            {colourise(out)}
          </pre>
        )}
      </div>
    </div>
  );
}

/** Tag git-diff lines with subtle colour. */
function colourise(text: string): React.ReactNode {
  const lines = text.split('\n');
  return lines.map((line, i) => {
    let className = '';
    if (line.startsWith('+++') || line.startsWith('---')) className = 'text-fg';
    else if (line.startsWith('+')) className = 'text-emerald-300';
    else if (line.startsWith('-')) className = 'text-red-300';
    else if (line.startsWith('@@')) className = 'text-blue-300';
    else if (line.startsWith('diff ') || line.startsWith('index ')) className = 'text-fg';
    return (
      <span key={i} className={className}>
        {line}
        {'\n'}
      </span>
    );
  });
}
