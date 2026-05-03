import { useEffect, useRef, useState } from 'react';
import { Terminal as TerminalIcon, Send, Loader2, AlertCircle, Trash2 } from 'lucide-react';
import { cn } from '@/lib/cn';

const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BASE = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

interface Entry {
  cmd: string;
  out: string;
  err: string;
  exit_code: number | null;
  ts: string;
}

export default function TerminalPanel() {
  const [cmd, setCmd] = useState('');
  const [history, setHistory] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [history]);

  const run = async () => {
    if (!cmd.trim() || busy) return;
    const command = cmd.trim();
    setCmd('');
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`${BASE}/api/agent/tool`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'shell',
          input: { command },
          permission_mode: 'bypass',
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (!data.ok) {
        setHistory((h) => [...h, {
          cmd: command, out: '', err: data.error || 'failed', exit_code: 1,
          ts: new Date().toISOString(),
        }]);
      } else {
        const o = data.output ?? {};
        setHistory((h) => [...h, {
          cmd: command,
          out: String(o.stdout || ''),
          err: String(o.stderr || ''),
          exit_code: typeof o.exit_code === 'number' ? o.exit_code : null,
          ts: new Date().toISOString(),
        }]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-fg">
          <TerminalIcon size={14} className="text-accent" strokeWidth={1.75} />
          <span className="font-medium">Terminal</span>
          <span className="text-xs text-fg-subtle">agent workspace · 60s timeout</span>
        </div>
        {history.length > 0 && (
          <button
            onClick={() => setHistory([])}
            className="text-fg-muted hover:text-fg transition-colors"
            title="Clear"
          >
            <Trash2 size={12} strokeWidth={1.75} />
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-auto bg-bg p-3 font-mono text-[11.5px] leading-relaxed">
        {error && (
          <div className="text-amber-300 flex items-start gap-1.5 mb-2">
            <AlertCircle size={12} className="mt-0.5 shrink-0" /> {error}
          </div>
        )}
        {history.length === 0 && !error && (
          <div className="text-fg-subtle">Type a command below — runs server-side via the shell agent tool.</div>
        )}
        {history.map((h, i) => (
          <div key={i} className="mb-3">
            <div className="text-accent">$ {h.cmd}</div>
            {h.out && <div className="text-fg-muted whitespace-pre-wrap break-all">{h.out}</div>}
            {h.err && <div className="text-red-300 whitespace-pre-wrap break-all">{h.err}</div>}
            {h.exit_code !== null && h.exit_code !== 0 && (
              <div className="text-fg-subtle">[exit {h.exit_code}]</div>
            )}
          </div>
        ))}
      </div>

      <div className="p-2 border-t border-border-subtle flex items-center gap-1.5">
        <span className="text-accent text-xs font-mono pl-1">$</span>
        <input
          type="text"
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(); }}
          disabled={busy}
          placeholder="git status, ls, npm run typecheck…"
          className={cn(
            'flex-1 bg-transparent text-xs font-mono text-fg placeholder:text-fg-faint focus:outline-none px-1',
            busy && 'opacity-60',
          )}
        />
        <button
          onClick={run}
          disabled={busy || !cmd.trim()}
          className="h-7 px-2 inline-flex items-center gap-1 rounded text-xs bg-accent hover:bg-accent-hover text-white transition-colors disabled:opacity-40"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
        </button>
      </div>
    </div>
  );
}
