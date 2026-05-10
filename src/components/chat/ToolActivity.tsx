import { useState, useMemo } from 'react';
import {
  ChevronRight,
  ChevronDown,
  Check,
  X as XIcon,
  Loader2,
  Wrench,
  FileText,
  FileCode,
  Terminal as TerminalIcon,
  Search,
  Eye,
  Database,
  Activity,
  Save,
  FlaskConical,
  BookOpen,
  Globe,
  BrainCircuit,
} from 'lucide-react';
import { cn } from '@/lib/cn';

/**
 * A single tool call entry rendered inside an AI turn. Shape mirrors what
 * the streaming store keeps: id (unique), name (tool name),
 * input (arguments dict) and optional result ({ok, error}).
 */
export interface ToolActivityItem {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: { ok: boolean; output?: unknown; error?: string };
}

interface Props {
  items: ToolActivityItem[];
  /** When true, show a live "running" marker on unfinished items. */
  streaming?: boolean;
}

/**
 * ToolActivity — compact, expandable panel summarising the agent's tool
 * calls. Replaces the wall of purple bubbles with a single summary row
 * that expands to show each individual tool in a lightweight list.
 *
 * Design goals:
 *   - Quiet by default: one line regardless of how many tools fired.
 *   - Glance-friendly: status icons (running / done / error) + short args.
 *   - No scroll hijack: expands in-flow, doesn't take over the chat pane.
 */
export default function ToolActivity({ items, streaming = false }: Props) {
  const [expanded, setExpanded] = useState(false);

  const counts = useMemo(() => {
    const c = { running: 0, done: 0, error: 0 };
    for (const t of items) {
      if (!t.result) c.running++;
      else if (t.result.ok) c.done++;
      else c.error++;
    }
    return c;
  }, [items]);

  if (items.length === 0) return null;

  const hasRunning = counts.running > 0;
  const hasError = counts.error > 0;

  return (
    <div className="rounded-lg border border-border-subtle bg-bg-panel/60 overflow-hidden">
      {/* Summary row — click to toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-bg-hover/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown size={13} className="text-fg-subtle shrink-0" strokeWidth={1.75} />
        ) : (
          <ChevronRight size={13} className="text-fg-subtle shrink-0" strokeWidth={1.75} />
        )}
        <Wrench size={13} className="text-fg-muted shrink-0" strokeWidth={1.75} />
        <span className="text-xs text-fg-muted">
          {items.length} {items.length === 1 ? 'tool' : 'tools'}
        </span>
        <span className="flex-1" />
        <div className="flex items-center gap-2 text-[11px] font-mono">
          {hasRunning && (
            <span className="flex items-center gap-1 text-accent">
              <Loader2 size={10} className="animate-spin" strokeWidth={2} />
              {counts.running}
            </span>
          )}
          {counts.done > 0 && (
            <span className="flex items-center gap-0.5 text-emerald-500">
              <Check size={10} strokeWidth={2.5} />
              {counts.done}
            </span>
          )}
          {hasError && (
            <span className="flex items-center gap-0.5 text-red-400">
              <XIcon size={10} strokeWidth={2.5} />
              {counts.error}
            </span>
          )}
        </div>
      </button>

      {/* Expanded list */}
      {expanded && (
        <div className="border-t border-border-subtle/60 divide-y divide-border-subtle/40">
          {items.map((t) => (
            <ToolRow key={t.id} item={t} streaming={streaming} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Icon per tool name ─────────────────────────────────────────────────

const TOOL_ICON: Record<string, typeof Wrench> = {
  bash: TerminalIcon,
  background_run: TerminalIcon,
  check_background: TerminalIcon,
  read_file: FileText,
  write_file: FileCode,
  edit_file: FileCode,
  load_skill: BookOpen,
  save_skill: BookOpen,
  patch_skill: BookOpen,
  backtest: FlaskConical,
  factor_analysis: Activity,
  options_pricing: Activity,
  pattern: Eye,
  web_search: Search,
  read_url: Globe,
  read_document: FileText,
  remember: Save,
  forget: XIcon,
  session_search: Search,
  compact: BrainCircuit,
  get_market_data: Database,
  run_swarm: BrainCircuit,
};

function iconFor(name: string) {
  return TOOL_ICON[name] || Wrench;
}

// ── Per-row renderer ───────────────────────────────────────────────────

function ToolRow({ item, streaming }: { item: ToolActivityItem; streaming: boolean }) {
  const Icon = iconFor(item.name);
  const done = !!item.result;
  const ok = item.result?.ok === true;
  const error = item.result?.ok === false;

  const label = useMemo(() => summarize(item.name, item.input), [item.name, item.input]);

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-xs">
      <Icon
        size={12}
        strokeWidth={1.75}
        className={cn(
          'shrink-0',
          error ? 'text-red-400' : ok ? 'text-emerald-500' : 'text-fg-subtle',
        )}
      />
      <span className="font-mono text-fg-muted shrink-0">{item.name}</span>
      {label && (
        <span className="text-fg-subtle truncate font-mono">{label}</span>
      )}
      <span className="flex-1" />
      {!done && streaming && (
        <Loader2 size={11} className="text-accent animate-spin shrink-0" strokeWidth={2} />
      )}
      {done && ok && (
        <Check size={11} className="text-emerald-500 shrink-0" strokeWidth={2.5} />
      )}
      {done && error && (
        <span className="text-red-400 truncate max-w-[160px]" title={item.result?.error || 'error'}>
          {item.result?.error || 'error'}
        </span>
      )}
    </div>
  );
}

/**
 * Turn a tool's input dict into a single short line.
 * Keeps things readable without exposing internals.
 */
function summarize(name: string, input: Record<string, unknown>): string {
  if (!input || Object.keys(input).length === 0) return '';

  // Tool-specific nice summaries
  switch (name) {
    case 'bash':
    case 'background_run':
      return truncate(String(input.command ?? ''), 80);
    case 'read_file':
    case 'write_file':
    case 'edit_file':
      return truncate(String(input.path ?? input.file_path ?? ''), 60);
    case 'load_skill':
    case 'save_skill':
    case 'patch_skill':
      return truncate(String(input.name ?? ''), 40);
    case 'backtest':
    case 'run_shadow_backtest':
      return truncate(String(input.run_dir ?? input.shadow_id ?? ''), 40);
    case 'web_search':
      return truncate(String(input.query ?? ''), 60);
    case 'read_url':
      return truncate(String(input.url ?? ''), 60);
    case 'read_document':
      return truncate(String(input.file_path ?? input.path ?? ''), 60);
    case 'run_swarm':
      return truncate(String(input.preset_name ?? input.preset ?? ''), 40);
    case 'compact':
      return input.focus_topic ? truncate(String(input.focus_topic), 40) : '';
  }

  // Generic fallback — first non-empty value
  for (const v of Object.values(input)) {
    if (v != null && v !== '') {
      const s = typeof v === 'string' ? v : JSON.stringify(v);
      return truncate(s, 60);
    }
  }
  return '';
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + '…';
}
