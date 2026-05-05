import { useEffect, useState, useRef } from 'react';
import {
  Activity, Play, Square, RefreshCw, Terminal as TerminalIcon,
  Globe, Clock, Wifi, WifiOff, Trash2, ChevronDown, ChevronUp,
  Loader2, Zap,
} from 'lucide-react';
import { cn } from '@/lib/cn';

const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BASE = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

interface ManagedProcess {
  id: string;
  command: string;
  cwd: string;
  pid: number;
  alive: boolean;
  exit_code: number | null;
  ready: boolean;
  detected_port: number | null;
  label: string | null;
  started_at: number;
  uptime_sec: number;
}

function formatUptime(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${h}h ${m}m`;
}

export default function RuntimePanel() {
  const [processes, setProcesses] = useState<ManagedProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [logs, setLogs] = useState<Record<string, string[]>>({});
  const [logLoading, setLogLoading] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchProcesses = async () => {
    try {
      const resp = await fetch(`${BASE}/api/processes`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setProcesses(data.processes || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProcesses();
    intervalRef.current = setInterval(fetchProcesses, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const fetchLogs = async (procId: string) => {
    setLogLoading(procId);
    try {
      const resp = await fetch(`${BASE}/api/processes/${procId}/output?last_n=80`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setLogs((prev) => ({ ...prev, [procId]: data.lines || [] }));
    } catch {
      setLogs((prev) => ({ ...prev, [procId]: ['[Failed to load logs]'] }));
    } finally {
      setLogLoading(null);
    }
  };

  const toggleExpand = (procId: string) => {
    if (expandedId === procId) {
      setExpandedId(null);
    } else {
      setExpandedId(procId);
      fetchLogs(procId);
    }
  };

  const stopProcess = async (procId: string) => {
    try {
      await fetch(`${BASE}/api/processes/${procId}`, { method: 'DELETE' });
      fetchProcesses();
    } catch { /* ignore */ }
  };

  const restartProcess = async (procId: string) => {
    try {
      await fetch(`${BASE}/api/processes/${procId}/restart`, { method: 'POST' });
      fetchProcesses();
    } catch { /* ignore */ }
  };

  const aliveCount = processes.filter((p) => p.alive).length;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-fg">
          <Activity size={14} className="text-accent" strokeWidth={1.75} />
          <span className="font-medium">Runtime</span>
          <span className="text-xs text-fg-subtle">
            {aliveCount} process{aliveCount !== 1 ? 'es' : ''} running
          </span>
        </div>
        <button
          onClick={fetchProcesses}
          className="text-fg-muted hover:text-fg transition-colors p-1 rounded hover:bg-bg-hover"
          title="Refresh"
        >
          <RefreshCw size={12} strokeWidth={1.75} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {loading && (
          <div className="flex items-center justify-center py-8 text-fg-muted text-xs">
            <Loader2 size={14} className="animate-spin mr-2" /> Loading processes…
          </div>
        )}

        {error && (
          <div className="text-amber-300 text-xs px-2 py-1.5 bg-amber-400/10 rounded">
            ⚠ {error}
          </div>
        )}

        {!loading && processes.length === 0 && !error && (
          <div className="text-center py-8 space-y-2">
            <div className="w-10 h-10 rounded-full bg-bg-hover flex items-center justify-center mx-auto">
              <Zap size={18} className="text-fg-subtle" strokeWidth={1.5} />
            </div>
            <p className="text-fg-muted text-xs">No managed processes</p>
            <p className="text-[11px] text-fg-subtle max-w-[220px] mx-auto leading-relaxed">
              The AI will start processes here when building and running apps.
              Use <span className="font-mono text-fg-muted">start_process</span> in chat.
            </p>
          </div>
        )}

        {processes.map((proc) => (
          <div
            key={proc.id}
            className={cn(
              'rounded-lg border transition-all',
              proc.alive
                ? 'border-border-subtle bg-bg-sidebar'
                : 'border-border-subtle/50 bg-bg-sidebar/50 opacity-70',
            )}
          >
            {/* Process row */}
            <div className="flex items-center gap-2 px-3 py-2">
              {/* Status dot */}
              <div className={cn(
                'w-2 h-2 rounded-full shrink-0',
                proc.alive && proc.ready ? 'bg-emerald-400 shadow-[0_0_6px_rgba(74,222,128,0.4)]' :
                proc.alive && !proc.ready ? 'bg-amber-400 animate-pulse' :
                'bg-red-400',
              )} />

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-fg truncate">
                    {proc.label || proc.command.split(' ')[0]}
                  </span>
                  {proc.detected_port && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/15 text-accent font-mono">
                      :{proc.detected_port}
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-fg-subtle font-mono truncate mt-0.5">
                  {proc.command}
                </div>
              </div>

              {/* Uptime */}
              <div className="flex items-center gap-1 text-[10px] text-fg-subtle shrink-0">
                <Clock size={9} />
                {formatUptime(proc.uptime_sec)}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-0.5 shrink-0">
                {proc.detected_port && proc.alive && (
                  <button
                    onClick={() => window.open(`http://localhost:${proc.detected_port}`, '_blank')}
                    className="p-1 rounded text-fg-muted hover:text-accent hover:bg-bg-hover transition-colors"
                    title="Open in browser"
                  >
                    <Globe size={11} strokeWidth={1.75} />
                  </button>
                )}
                {proc.alive && (
                  <button
                    onClick={() => restartProcess(proc.id)}
                    className="p-1 rounded text-fg-muted hover:text-amber-400 hover:bg-bg-hover transition-colors"
                    title="Restart"
                  >
                    <RefreshCw size={11} strokeWidth={1.75} />
                  </button>
                )}
                {proc.alive && (
                  <button
                    onClick={() => stopProcess(proc.id)}
                    className="p-1 rounded text-fg-muted hover:text-red-400 hover:bg-bg-hover transition-colors"
                    title="Stop"
                  >
                    <Square size={11} strokeWidth={1.75} />
                  </button>
                )}
                <button
                  onClick={() => toggleExpand(proc.id)}
                  className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
                  title="Logs"
                >
                  {expandedId === proc.id
                    ? <ChevronUp size={11} strokeWidth={1.75} />
                    : <ChevronDown size={11} strokeWidth={1.75} />
                  }
                </button>
              </div>
            </div>

            {/* Expanded log viewer */}
            {expandedId === proc.id && (
              <div className="border-t border-border-subtle bg-bg px-3 py-2 max-h-48 overflow-auto">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] text-fg-subtle font-mono">{proc.id} · PID {proc.pid}</span>
                  <button
                    onClick={() => fetchLogs(proc.id)}
                    className="text-[10px] text-fg-muted hover:text-fg transition-colors"
                  >
                    {logLoading === proc.id ? <Loader2 size={10} className="animate-spin" /> : 'Refresh'}
                  </button>
                </div>
                <div className="font-mono text-[10.5px] leading-relaxed space-y-px">
                  {(logs[proc.id] || []).length === 0 && (
                    <div className="text-fg-subtle italic">No output yet</div>
                  )}
                  {(logs[proc.id] || []).map((line, i) => (
                    <div key={i} className={cn(
                      'whitespace-pre-wrap break-all',
                      /error|ERR|fail/i.test(line) ? 'text-red-300' :
                      /warn/i.test(line) ? 'text-amber-300' :
                      'text-fg-muted',
                    )}>
                      {line}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
