import { useState } from 'react';
import { Plus, Trash2, ListChecks, Check, Circle, CircleDot } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore, useActiveSession, type TaskItem } from '@/store/useAppStore';

const STATUS_ICON = {
  pending: Circle,
  in_progress: CircleDot,
  done: Check,
};

export default function TasksPanel() {
  const session = useActiveSession();
  const sessionId = session?.id ?? null;
  const tasks: TaskItem[] = useAppStore((s) =>
    sessionId ? s.tasksBySession[sessionId] ?? [] : [],
  );
  const addTask = useAppStore((s) => s.addTask);
  const updateTask = useAppStore((s) => s.updateTask);
  const removeTask = useAppStore((s) => s.removeTask);
  const clearDone = useAppStore((s) => s.clearDoneTasks);
  const [draft, setDraft] = useState('');

  if (!sessionId) {
    return (
      <div className="flex-1 flex items-center justify-center text-fg-muted text-sm p-6">
        Open a session to manage tasks.
      </div>
    );
  }

  const cycle = (t: TaskItem) => {
    const next = t.status === 'pending'
      ? 'in_progress'
      : t.status === 'in_progress' ? 'done' : 'pending';
    updateTask(sessionId, t.id, { status: next });
  };

  const submit = () => {
    if (draft.trim()) {
      addTask(sessionId, draft);
      setDraft('');
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-fg">
          <ListChecks size={14} className="text-accent" strokeWidth={1.75} />
          <span className="font-medium">Tasks</span>
          <span className="text-xs text-fg-subtle">
            {tasks.filter((t) => t.status !== 'done').length} open · {tasks.filter((t) => t.status === 'done').length} done
          </span>
        </div>
        {tasks.some((t) => t.status === 'done') && (
          <button
            onClick={() => clearDone(sessionId)}
            className="text-[11px] text-fg-muted hover:text-fg transition-colors"
          >
            Clear done
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
        {tasks.length === 0 ? (
          <div className="text-xs text-fg-subtle text-center py-6">
            No tasks yet. Add one below or ask the AI to plan a task list.
          </div>
        ) : (
          tasks.map((t) => {
            const StatusIcon = STATUS_ICON[t.status];
            return (
              <div
                key={t.id}
                className={cn(
                  'flex items-start gap-2 rounded-md border border-border-subtle px-2.5 py-2',
                  t.status === 'done' && 'opacity-60',
                )}
              >
                <button
                  onClick={() => cycle(t)}
                  className={cn(
                    'mt-0.5 shrink-0 transition-colors',
                    t.status === 'done' ? 'text-emerald-400' : t.status === 'in_progress' ? 'text-amber-400' : 'text-fg-muted hover:text-fg',
                  )}
                  title={`status: ${t.status}`}
                >
                  <StatusIcon size={13} strokeWidth={2} />
                </button>
                <input
                  type="text"
                  value={t.title}
                  onChange={(e) => updateTask(sessionId, t.id, { title: e.target.value })}
                  className={cn(
                    'flex-1 bg-transparent text-sm focus:outline-none',
                    t.status === 'done' && 'line-through text-fg-muted',
                  )}
                />
                <button
                  onClick={() => removeTask(sessionId, t.id)}
                  className="text-fg-muted hover:text-red-300 transition-colors shrink-0"
                  title="Remove"
                >
                  <Trash2 size={12} strokeWidth={1.75} />
                </button>
              </div>
            );
          })
        )}
      </div>

      <div className="p-3 border-t border-border-subtle flex items-center gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
          placeholder="New task…"
          className="flex-1 px-2.5 py-1.5 rounded bg-bg border border-border text-xs text-fg placeholder:text-fg-faint focus:outline-none focus:border-border-strong"
        />
        <button
          onClick={submit}
          disabled={!draft.trim()}
          className="h-7 px-2 inline-flex items-center gap-1 rounded text-xs bg-accent hover:bg-accent-hover text-white transition-colors disabled:opacity-40"
        >
          <Plus size={12} />
          Add
        </button>
      </div>
    </div>
  );
}
