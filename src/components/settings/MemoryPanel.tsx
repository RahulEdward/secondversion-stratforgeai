import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2, BookOpen, Plus, Save, Trash2, X, AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';
import {
  listMemory, getMemory, upsertMemory, deleteMemory,
  type MemorySummary, type MemoryEntry, type MemoryType,
} from '@/lib/api';

type Editor = {
  isNew: boolean;
  name: string;
  title: string;
  description: string;
  type: MemoryType;
  body: string;
};

const TYPE_BADGES: Record<MemoryType, string> = {
  user: 'bg-blue-500/15 text-blue-300 border border-blue-500/20',
  feedback: 'bg-amber-500/15 text-amber-300 border border-amber-500/20',
  project: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20',
  reference: 'bg-white/5 text-fg-subtle border border-white/10',
};

const NEW_EDITOR: Editor = {
  isNew: true,
  name: '',
  title: '',
  description: '',
  type: 'reference',
  body: '',
};

export default function MemoryPanel() {
  const projects = useAppStore((s) => s.projects);
  const activeProjectId = useAppStore((s) => s.activeProjectId);

  // Pick the active project; if none, fall back to the first.
  const projectId = activeProjectId ?? projects[0]?.id ?? null;
  const projectName = useMemo(
    () => projects.find((p) => p.id === projectId)?.name ?? '',
    [projects, projectId],
  );

  const [list, setList] = useState<MemorySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!projectId) {
      setList([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setList(await listMemory(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memory');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openEditor = async (m: MemorySummary) => {
    if (!projectId) return;
    try {
      const full: MemoryEntry = await getMemory(projectId, m.name);
      setEditor({
        isNew: false,
        name: full.name,
        title: full.title,
        description: full.description,
        type: full.type,
        body: full.body,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load entry');
    }
  };

  const save = async () => {
    if (!projectId || !editor) return;
    const slug = editor.name.trim() || editor.title.trim().toLowerCase().replace(/\s+/g, '_');
    if (!slug) {
      setError('Title or name is required.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await upsertMemory(projectId, slug, {
        title: editor.title || slug,
        description: editor.description,
        body: editor.body,
        type: editor.type,
      });
      setEditor(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (m: MemorySummary) => {
    if (!projectId) return;
    if (!confirm(`Delete memory "${m.title}"?`)) return;
    setBusy(true);
    try {
      await deleteMemory(projectId, m.name);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  if (!projectId) {
    return (
      <div className="flex-1 flex items-center justify-center text-fg-muted text-sm p-8">
        No project selected. Create or open a project first.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-8 py-8">
        <header className="mb-6 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold flex items-center gap-2">
              <BookOpen size={16} className="text-accent" strokeWidth={1.75} />
              Memory
            </h1>
            <p className="text-sm text-fg-muted mt-1">
              Durable learnings for project <span className="font-medium text-fg">{projectName}</span>.
              Auto-distilled every 10 messages and prepended to the system prompt on every turn.
            </p>
          </div>
          <button
            onClick={() => setEditor({ ...NEW_EDITOR })}
            className={cn(
              'h-8 px-3 inline-flex items-center gap-1.5 rounded text-xs',
              'bg-accent hover:bg-accent-hover text-white transition-colors',
            )}
          >
            <Plus size={13} strokeWidth={1.75} />
            New entry
          </button>
        </header>

        {error && (
          <div className="mb-3 flex items-start gap-1.5 text-xs text-amber-300">
            <AlertCircle size={13} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {loading && list.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-fg-muted">
            <Loader2 size={14} className="animate-spin" />
            Loading…
          </div>
        ) : list.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-subtle p-6 text-center">
            <p className="text-sm text-fg-muted">No memory entries yet.</p>
            <p className="text-xs text-fg-subtle mt-1">
              Memory is auto-generated as you chat, or click <span className="text-fg">New entry</span> to add one manually.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {list.map((m) => (
              <article
                key={m.name}
                onClick={() => openEditor(m)}
                className={cn(
                  'rounded-xl border border-border-subtle bg-bg-sidebar p-4 cursor-pointer',
                  'hover:bg-bg-hover transition-colors',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-medium truncate">{m.title}</h3>
                      <span className={cn('text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider', TYPE_BADGES[m.type])}>
                        {m.type}
                      </span>
                    </div>
                    <p className="text-xs text-fg-muted mt-1 line-clamp-2">{m.description || '—'}</p>
                    <p className="text-[10px] text-fg-subtle mt-1.5 font-mono">
                      {m.name}.md · updated {new Date(m.updated_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); void remove(m); }}
                    className="text-fg-muted hover:text-red-300 transition-colors p-1 -m-1 shrink-0"
                    title="Delete"
                  >
                    <Trash2 size={13} strokeWidth={1.75} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      {/* Editor overlay */}
      {editor && (
        <div
          data-settings-dialog="true"
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4"
          onClick={() => !busy && setEditor(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl bg-bg-panel border border-border-subtle rounded-xl shadow-popup max-h-[85vh] flex flex-col"
          >
            <header className="flex items-center justify-between px-5 py-3.5 border-b border-border-subtle">
              <h2 className="text-sm font-medium">
                {editor.isNew ? 'New memory entry' : `Edit · ${editor.title}`}
              </h2>
              <button
                onClick={() => setEditor(null)}
                disabled={busy}
                className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover"
              >
                <X size={14} strokeWidth={1.75} />
              </button>
            </header>

            <div className="px-5 py-4 space-y-3 overflow-y-auto">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-fg-muted mb-1">Title</label>
                  <input
                    type="text"
                    value={editor.title}
                    onChange={(e) => setEditor({ ...editor, title: e.target.value })}
                    className="w-full px-3 py-2 rounded bg-bg border border-border text-sm text-fg focus:outline-none focus:border-border-strong"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-fg-muted mb-1">Type</label>
                  <select
                    value={editor.type}
                    onChange={(e) => setEditor({ ...editor, type: e.target.value as MemoryType })}
                    className="w-full px-3 py-2 rounded bg-bg border border-border text-sm text-fg focus:outline-none focus:border-border-strong"
                  >
                    <option value="user">user — preferences</option>
                    <option value="feedback">feedback — corrections</option>
                    <option value="project">project — project-specific</option>
                    <option value="reference">reference — general</option>
                  </select>
                </div>
              </div>

              {editor.isNew && (
                <div>
                  <label className="block text-xs font-medium text-fg-muted mb-1">
                    Slug <span className="text-fg-subtle">(filename — auto from title if blank)</span>
                  </label>
                  <input
                    type="text"
                    value={editor.name}
                    onChange={(e) => setEditor({ ...editor, name: e.target.value })}
                    placeholder="e.g. btc_low_freq_pref"
                    className="w-full px-3 py-2 rounded bg-bg border border-border text-sm font-mono text-fg focus:outline-none focus:border-border-strong"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-fg-muted mb-1">Description</label>
                <input
                  type="text"
                  value={editor.description}
                  onChange={(e) => setEditor({ ...editor, description: e.target.value })}
                  placeholder="One-line summary"
                  className="w-full px-3 py-2 rounded bg-bg border border-border text-sm text-fg focus:outline-none focus:border-border-strong"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-fg-muted mb-1">Body (markdown)</label>
                <textarea
                  value={editor.body}
                  onChange={(e) => setEditor({ ...editor, body: e.target.value })}
                  rows={12}
                  className="w-full px-3 py-2 rounded bg-bg border border-border text-xs font-mono text-fg focus:outline-none focus:border-border-strong resize-none"
                />
              </div>
            </div>

            <footer className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-subtle">
              <button
                onClick={() => setEditor(null)}
                disabled={busy}
                className="h-8 px-3 text-xs rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={save}
                disabled={busy}
                className="h-8 px-3 inline-flex items-center gap-1.5 rounded text-xs bg-accent hover:bg-accent-hover text-white transition-colors disabled:opacity-50"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} strokeWidth={1.75} />}
                {editor.isNew ? 'Create' : 'Save'}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
