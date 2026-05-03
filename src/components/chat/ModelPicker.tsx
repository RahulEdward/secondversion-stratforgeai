import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, AlertCircle, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/cn';
import Popup from '../ui/Popup';
import { toast } from '../ui/Toast';
import { useActiveSession, useAppStore } from '@/store/useAppStore';
import {
  listProviderModels,
  type ProviderInfo,
  type ProviderModel,
} from '@/lib/api';

type SortKey = 'name' | 'context';

interface Row {
  provider: ProviderInfo;
  model: ProviderModel;
}

interface CacheEntry {
  loading: boolean;
  models: ProviderModel[];
  error: string | null;
}

/** Drop provider prefix / vendor tag from a model id for the header button. */
function shortLabel(label: string): string {
  return label
    .replace(/^(Anthropic|OpenAI|Google|Ollama)\s*[·:\-]\s*/i, '')
    .replace(/^claude-/i, 'Claude ')
    .replace(/^gpt-/i, 'GPT-')
    .replace(/^gemini-/i, 'Gemini ');
}

export default function ModelPicker() {
  const [open, setOpen] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [providerFilter, setProviderFilter] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, CacheEntry>>({});

  const providers = useAppStore((s) => s.providers);
  const refreshProviders = useAppStore((s) => s.refreshProviders);
  const updateSessionModel = useAppStore((s) => s.updateSessionModel);
  const openSettings = useAppStore((s) => s.openSettings);
  const session = useActiveSession();
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const projects = useAppStore((s) => s.projects);
  const createProject = useAppStore((s) => s.createProject);
  const createSession = useAppStore((s) => s.createSession);

  const configured = useMemo(
    () =>
      providers.filter((p) =>
        p.kind === 'local' ? p.reachable === true : p.has_credential,
      ),
    [providers],
  );

  const headerLabel = useMemo(() => {
    if (!session?.provider || !session?.model) return 'Select model';
    const p = providers.find((x) => x.name === session.provider);
    const cached = cache[session.provider]?.models.find(
      (m) => m.id === session.model,
    );
    return shortLabel(cached?.label ?? session.model ?? p?.label ?? '');
  }, [providers, session, cache]);

  // Refresh providers when popup opens so newly-connected providers (e.g. ChatGPT after OAuth) appear.
  // Models cache is preserved between opens — first open after sign-in fetches, subsequent opens are instant.
  useEffect(() => {
    if (!open) return;
    refreshProviders();
  }, [open, refreshProviders]);

  // When a provider becomes newly-credentialed (e.g. ChatGPT after OAuth), drop its stale cache
  // entry so the next render re-fetches its models.
  useEffect(() => {
    setCache((c) => {
      let changed = false;
      const next = { ...c };
      for (const p of configured) {
        const entry = next[p.name];
        // Drop entries that errored — provider may now be reachable.
        if (entry && entry.error) {
          delete next[p.name];
          changed = true;
        }
      }
      return changed ? next : c;
    });
  }, [configured]);

  useEffect(() => {
    if (!open) return;
    configured.forEach((p) => {
      if (cache[p.name]) return;
      setCache((c) => ({
        ...c,
        [p.name]: { loading: true, models: [], error: null },
      }));
      listProviderModels(p.name)
        .then((models) =>
          setCache((c) => ({
            ...c,
            [p.name]: { loading: false, models, error: null },
          })),
        )
        .catch((err) =>
          setCache((c) => ({
            ...c,
            [p.name]: {
              loading: false,
              models: [],
              error: err instanceof Error ? err.message : 'Failed to load',
            },
          })),
        );
    });
  }, [open, configured, cache]);

  const rows = useMemo<Row[]>(() => {
    const list: Row[] = [];
    for (const p of configured) {
      if (providerFilter && providerFilter !== p.name) continue;
      const entry = cache[p.name];
      if (!entry) continue;
      for (const m of entry.models) list.push({ provider: p, model: m });
    }
    list.sort((a, b) => {
      if (sortKey === 'context') {
        const ac = a.model.context_window ?? 0;
        const bc = b.model.context_window ?? 0;
        if (ac !== bc) return bc - ac;
      }
      return a.model.label.localeCompare(b.model.label);
    });
    return list;
  }, [configured, cache, providerFilter, sortKey]);

  const anyLoading = configured.some((p) => cache[p.name]?.loading);
  const errors = configured
    .map((p) => ({ name: p.label, err: cache[p.name]?.error }))
    .filter((e) => e.err);

  const handlePick = async (row: Row) => {
    try {
      // Ensure we have an active session — auto-create project + session if needed.
      let sessionId = session?.id ?? null;
      if (!sessionId) {
        let projectId = activeProjectId ?? projects[0]?.id ?? null;
        if (!projectId) {
          const p = await createProject('My Project');
          projectId = p.id;
        }
        const s = await createSession(projectId, 'New session');
        sessionId = s.id;
      }
      await updateSessionModel(sessionId, row.provider.name, row.model.id);
      toast(`Switched to ${row.provider.label} · ${row.model.label}`);
      setOpen(false);
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to set model');
    }
  };

  const formatContext = (n: number | null) => {
    if (!n) return null;
    if (n >= 1000) return `${Math.round(n / 1000)}K ctx`;
    return `${n} ctx`;
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'h-7 flex items-center gap-1.5 px-2 rounded text-xs',
          'text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors',
        )}
      >
        <span className="truncate max-w-[180px]">{headerLabel}</span>
        <ChevronDown size={11} strokeWidth={1.75} />
      </button>
      {open && (
        <Popup
          open
          onClose={() => setOpen(false)}
          className="bottom-9 right-0 w-[340px] max-h-[480px] flex flex-col overflow-hidden"
        >
          {/* Sort + provider chips */}
          <div className="px-2.5 pt-2 pb-1.5 flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() =>
                setSortKey((k) => (k === 'name' ? 'context' : 'name'))
              }
              className={cn(
                'h-6 px-1.5 rounded flex items-center gap-1 text-[11px]',
                'text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors',
              )}
            >
              <ArrowUpDown size={10} strokeWidth={1.75} />
              {sortKey === 'name' ? 'Name' : 'Context'}
            </button>
            {configured.length > 1 && (
              <>
                <span className="text-fg-faint text-[10px]">·</span>
                <button
                  onClick={() => setProviderFilter(null)}
                  className={cn(
                    'h-6 px-2 rounded-full text-[11px] transition-colors',
                    providerFilter === null
                      ? 'bg-bg-hover text-fg'
                      : 'text-fg-muted hover:bg-bg-hover',
                  )}
                >
                  All
                </button>
                {configured.map((p) => (
                  <button
                    key={p.name}
                    onClick={() =>
                      setProviderFilter((cur) => (cur === p.name ? null : p.name))
                    }
                    className={cn(
                      'h-6 px-2 rounded-full text-[11px] transition-colors',
                      providerFilter === p.name
                        ? 'bg-bg-hover text-fg'
                        : 'text-fg-muted hover:bg-bg-hover',
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </>
            )}
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto border-t border-border-subtle">
            {configured.length === 0 && (
              <div className="px-3 py-4 text-xs text-fg-muted text-center">
                No providers configured.{' '}
                <button
                  onClick={() => {
                    openSettings('providers');
                    setOpen(false);
                  }}
                  className="text-fg underline underline-offset-2"
                >
                  Open Settings
                </button>
              </div>
            )}
            {errors.map((e) => (
              <div
                key={e.name}
                className="px-3 py-1.5 text-[11px] text-amber-300 flex items-start gap-1.5"
              >
                <AlertCircle size={11} className="mt-0.5 shrink-0" />
                <span>
                  {e.name}: {e.err}
                </span>
              </div>
            ))}
            {rows.length === 0 && configured.length > 0 && !anyLoading && (
              <div className="px-3 py-4 text-xs text-fg-muted text-center">
                No models returned.
              </div>
            )}
            {anyLoading && rows.length === 0 && (
              <div className="px-3 py-3 text-xs text-fg-muted text-center">
                Loading models…
              </div>
            )}
            {rows.map((r) => {
              const selected =
                session?.provider === r.provider.name &&
                session?.model === r.model.id;
              const ctx = formatContext(r.model.context_window);
              return (
                <button
                  key={`${r.provider.name}:${r.model.id}`}
                  onClick={() => handlePick(r)}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 text-left',
                    'hover:bg-bg-hover transition-colors',
                    selected && 'bg-bg-hover',
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm text-fg truncate">
                        {r.model.label}
                      </span>
                      <span className="text-[9px] font-medium uppercase tracking-wider px-1 py-px rounded bg-emerald-500/15 text-emerald-300">
                        Available
                      </span>
                    </div>
                    <div className="text-[10px] text-fg-subtle truncate">
                      {r.provider.label}
                      {ctx ? ` · ${ctx}` : ''}
                    </div>
                  </div>
                  {selected && (
                    <span className="text-fg-muted text-sm">✓</span>
                  )}
                </button>
              );
            })}
          </div>
        </Popup>
      )}
    </div>
  );
}
