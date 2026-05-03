import { useEffect, useState } from 'react';
import { Folder, FileText, ChevronRight, ChevronDown, RefreshCw, FolderOpen, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/cn';

const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BASE = WEB_ONLY ? '' : (ENV_URL && ENV_URL.length > 0 ? ENV_URL : 'http://127.0.0.1:8765');

interface ListEntry {
  name: string;
  type: 'file' | 'directory';
  size_bytes?: number;
  modified?: string;
}

/** Reuse the agent `list_dir` tool over a thin REST proxy. We don't have a
 *  dedicated files endpoint yet, so call the agent dispatcher directly. */
async function listDir(path: string): Promise<ListEntry[]> {
  const resp = await fetch(`${BASE}/api/agent/tool`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: 'list_dir',
      input: { path },
      permission_mode: 'plan',  // read-only — never blocked
    }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (!data.ok) throw new Error(data.error || 'list_dir failed');
  return (data.output?.entries ?? []) as ListEntry[];
}

interface NodeProps {
  path: string;
  name: string;
  type: 'file' | 'directory';
  depth: number;
}

function Node({ path, name, type, depth }: NodeProps) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<ListEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const expand = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (entries !== null) return;
    setLoading(true);
    try {
      const childPath = path ? `${path}/${name}` : name;
      setEntries(await listDir(childPath));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button
        onClick={type === 'directory' ? expand : undefined}
        disabled={type !== 'directory'}
        className={cn(
          'w-full flex items-center gap-1 py-1 px-1 rounded hover:bg-bg-hover transition-colors text-left',
          type !== 'directory' && 'cursor-default',
        )}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
      >
        {type === 'directory' ? (
          open ? <ChevronDown size={11} className="text-fg-subtle shrink-0" /> : <ChevronRight size={11} className="text-fg-subtle shrink-0" />
        ) : <span className="w-[11px] shrink-0" />}
        {type === 'directory' ? (
          open ? <FolderOpen size={12} className="text-amber-400 shrink-0" /> : <Folder size={12} className="text-amber-400 shrink-0" />
        ) : <FileText size={12} className="text-fg-muted shrink-0" />}
        <span className="text-xs text-fg truncate">{name}</span>
      </button>
      {open && type === 'directory' && (
        <div>
          {loading && <div className="text-[10px] text-fg-subtle pl-8 py-1">loading…</div>}
          {error && <div className="text-[10px] text-amber-300 pl-8 py-1 flex items-center gap-1"><AlertCircle size={10} />{error}</div>}
          {entries && entries.map((e) => (
            <Node
              key={`${path}/${name}/${e.name}`}
              path={path ? `${path}/${name}` : name}
              name={e.name}
              type={e.type}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FilesPanel() {
  const [root, setRoot] = useState<ListEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setRoot(await listDir(''));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-fg">
          <FolderOpen size={14} className="text-accent" strokeWidth={1.75} />
          <span className="font-medium">Agent workspace</span>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {error && (
          <div className="text-xs text-amber-300 px-3 py-2 flex items-start gap-1.5">
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {root && root.length === 0 && !error && (
          <div className="text-[11px] text-fg-subtle px-3 py-3">Empty.</div>
        )}
        {root && root.map((e) => (
          <Node key={e.name} path="" name={e.name} type={e.type} depth={0} />
        ))}
      </div>
    </div>
  );
}
