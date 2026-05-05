import { useEffect, useRef, useState } from 'react';
import {
  PanelRight, ChevronDown, Eye, GitCompare, Terminal as TerminalIcon,
  FolderOpen, ListChecks, ClipboardList, Activity,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore, type RightPaneMode, type PermissionMode } from '@/store/useAppStore';

interface MenuItem {
  id: Exclude<RightPaneMode, null> | 'plan';
  label: string;
  icon: typeof Eye;
  shortcut: string;
}

const ITEMS: MenuItem[] = [
  { id: 'preview', label: 'Preview', icon: Eye, shortcut: '⇧Ctrl P' },
  { id: 'diff', label: 'Diff', icon: GitCompare, shortcut: '⇧Ctrl D' },
  { id: 'terminal', label: 'Terminal', icon: TerminalIcon, shortcut: 'Ctrl `' },
  { id: 'runtime', label: 'Runtime', icon: Activity, shortcut: '⇧Ctrl R' },
  { id: 'files', label: 'Files', icon: FolderOpen, shortcut: '⇧Ctrl F' },
  { id: 'tasks', label: 'Tasks', icon: ListChecks, shortcut: '' },
  { id: 'plan', label: 'Plan', icon: ClipboardList, shortcut: '' },
];

export default function RightPaneMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const mode = useAppStore((s) => s.rightPaneMode);
  const setMode = useAppStore((s) => s.setRightPaneMode);
  const permission = useAppStore((s) => s.permissionMode);
  const setPermission = useAppStore((s) => s.setPermissionMode);
  const toggleArtifacts = useAppStore((s) => s.toggleArtifacts);
  const artifactsOpen = useAppStore((s) => s.artifactsOpen);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  // Global keyboard shortcuts (Claude Code parity).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey;
      const shift = e.shiftKey;
      if (ctrl && shift && (e.key === 'P' || e.key === 'p')) { e.preventDefault(); setMode('preview'); }
      else if (ctrl && shift && (e.key === 'D' || e.key === 'd')) { e.preventDefault(); setMode('diff'); }
      else if (ctrl && shift && (e.key === 'F' || e.key === 'f')) { e.preventDefault(); setMode('files'); }
      else if (ctrl && shift && (e.key === 'R' || e.key === 'r')) { e.preventDefault(); setMode('runtime'); }
      else if (ctrl && !shift && e.key === '`') { e.preventDefault(); setMode('terminal'); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setMode]);

  const select = (id: MenuItem['id']) => {
    setOpen(false);
    if (id === 'plan') {
      // Plan toggles permission mode.
      const next: PermissionMode = permission === 'plan' ? 'accept-edits' : 'plan';
      setPermission(next);
    } else {
      setMode(id);
    }
  };

  return (
    <div ref={ref} className="relative no-drag">
      <div className={cn(
        'flex items-center rounded overflow-hidden',
        artifactsOpen ? 'bg-bg-panel text-fg' : 'text-fg-muted bg-transparent'
      )}>
        <button
          onClick={toggleArtifacts}
          className={cn(
            'h-7 px-2 flex items-center justify-center transition-colors',
            'hover:text-fg hover:bg-bg-hover'
          )}
          title={artifactsOpen ? 'Hide panel' : 'Show panel'}
        >
          <PanelRight size={14} strokeWidth={1.75} />
        </button>
        <div className="w-[1px] h-4 bg-border-subtle" />
        <button
          onClick={() => setOpen((v) => !v)}
          className={cn(
            'h-7 px-1 flex items-center justify-center transition-colors',
            'hover:text-fg hover:bg-bg-hover'
          )}
          title="Panel menu"
        >
          <ChevronDown size={11} strokeWidth={1.75} />
        </button>
      </div>

      {open && (
        <div
          className={cn(
            'absolute right-0 top-9 z-50 w-[260px] rounded-lg shadow-popup',
            'bg-bg-panel border border-border-subtle py-1',
          )}
        >
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const active = (item.id === 'plan' && permission === 'plan')
              || (item.id !== 'plan' && mode === item.id);
            return (
              <button
                key={item.id}
                onClick={() => select(item.id)}
                className={cn(
                  'w-full flex items-center justify-between px-3 py-2 text-left text-sm',
                  'transition-colors',
                  active ? 'bg-bg-active text-fg' : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
                )}
              >
                <span className="flex items-center gap-2.5">
                  <Icon size={14} strokeWidth={1.75} />
                  <span>{item.label}</span>
                </span>
                {item.shortcut && (
                  <span className="text-[10px] text-fg-subtle font-mono">{item.shortcut}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
