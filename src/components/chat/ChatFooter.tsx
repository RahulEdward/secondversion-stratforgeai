import { useEffect, useRef, useState } from 'react';
import { Check, ChevronUp, Lock, Mic, Plus, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useActiveProject, useAppStore, type PermissionMode } from '@/store/useAppStore';
import { toast } from '../ui/Toast';
import ModelPicker from './ModelPicker';

const PERMISSION_MODES: Array<{ id: PermissionMode; label: string; key: string }> = [
  { id: 'ask', label: 'Ask permissions', key: '1' },
  { id: 'accept-edits', label: 'Accept edits', key: '2' },
  { id: 'plan', label: 'Plan mode', key: '3' },
  { id: 'bypass', label: 'Bypass permissions', key: '4' },
];

function IconBtn({
  title,
  onClick,
  active,
  children,
  trailing,
}: {
  title: string;
  onClick?: () => void;
  active?: boolean;
  children: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        'h-7 flex items-center gap-0.5 px-1.5 rounded',
        'transition-colors',
        active
          ? 'text-red-300 bg-red-500/10'
          : 'text-fg-muted hover:text-fg hover:bg-bg-hover',
      )}
    >
      {children}
      {trailing}
    </button>
  );
}

// Web Speech API typing — minimal subset we use.
type SR = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: SpeechRecognitionEvent) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
};
interface SpeechRecognitionEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
  resultIndex: number;
}

function getSpeechRecognition(): { new (): SR } | null {
  const w = window as unknown as {
    SpeechRecognition?: { new (): SR };
    webkitSpeechRecognition?: { new (): SR };
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export default function ChatFooter() {
  const permissionMode = useAppStore((s) => s.permissionMode);
  const setPermissionMode = useAppStore((s) => s.setPermissionMode);
  const appendChatDraft = useAppStore((s) => s.appendChatDraft);
  const setChatDraft = useAppStore((s) => s.setChatDraft);
  const draft = useAppStore((s) => s.chatDraft);
  const uploadDataset = useAppStore((s) => s.uploadDataset);
  const createProject = useAppStore((s) => s.createProject);
  const projects = useAppStore((s) => s.projects);
  const project = useActiveProject();

  const fileRef = useRef<HTMLInputElement>(null);
  const recRef = useRef<SR | null>(null);
  const draftAtStartRef = useRef<string>('');
  const [listening, setListening] = useState(false);
  const [modeOpen, setModeOpen] = useState(false);
  const modeBtnRef = useRef<HTMLButtonElement>(null);
  const modePopupRef = useRef<HTMLDivElement>(null);

  const currentMode = PERMISSION_MODES.find((m) => m.id === permissionMode) ?? PERMISSION_MODES[1];

  // Cleanup mic on unmount.
  useEffect(() => {
    return () => {
      try { recRef.current?.stop(); } catch { /* noop */ }
    };
  }, []);

  // Close mode popup on outside click + Escape.
  useEffect(() => {
    if (!modeOpen) return;
    const onClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (modePopupRef.current?.contains(t) || modeBtnRef.current?.contains(t)) return;
      setModeOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setModeOpen(false); return; }
      // Number shortcuts 1–4 while popup is open.
      const m = PERMISSION_MODES.find((x) => x.key === e.key);
      if (m) {
        setPermissionMode(m.id);
        setModeOpen(false);
      }
    };
    const t = setTimeout(() => {
      document.addEventListener('mousedown', onClick);
      document.addEventListener('keydown', onKey);
    }, 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [modeOpen, setPermissionMode]);

  // Global Shift+Ctrl+M to cycle through modes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'M' || e.key === 'm')) {
        e.preventDefault();
        const idx = PERMISSION_MODES.findIndex((m) => m.id === permissionMode);
        const next = PERMISSION_MODES[(idx + 1) % PERMISSION_MODES.length];
        setPermissionMode(next.id);
        toast(`Mode: ${next.label}`);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [permissionMode, setPermissionMode]);

  // ── Plus button: pick a file → upload as dataset (CSV) or attach name to draft ──
  const handlePlusClick = () => fileRef.current?.click();

  const handleFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow same file again
    if (!file) return;

    const isCsv = /\.csv$/i.test(file.name) || file.type === 'text/csv';
    if (isCsv) {
      // Ensure we have a project to attach the dataset to.
      let projectId = project?.id ?? projects[0]?.id ?? null;
      if (!projectId) {
        try {
          const p = await createProject('My Project');
          projectId = p.id;
        } catch (err) {
          toast(err instanceof Error ? err.message : 'Failed to create project');
          return;
        }
      }
      toast(`Uploading ${file.name}…`);
      try {
        const ds = await uploadDataset(projectId, file);
        toast(`Dataset uploaded · ${ds.rows} rows`);
        appendChatDraft(`(attached dataset: ${ds.filename}, id=${ds.id})`);
      } catch (err) {
        toast(err instanceof Error ? err.message : 'Upload failed');
      }
    } else {
      // Non-CSV — read as text and reference name in the draft.
      try {
        const text = await file.text();
        const snippet = text.slice(0, 4000);
        appendChatDraft(`\n\n--- ${file.name} ---\n${snippet}${text.length > 4000 ? '\n…(truncated)' : ''}`);
        toast(`Attached ${file.name}`);
      } catch {
        toast(`Attached ${file.name}`);
        appendChatDraft(`(attached file: ${file.name})`);
      }
    }
  };

  // ── Mic button: Web Speech API toggle ──
  const handleMicClick = () => {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      toast('Voice input not supported in this build');
      return;
    }

    if (listening) {
      try { recRef.current?.stop(); } catch { /* noop */ }
      return;
    }

    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'en-US';
    draftAtStartRef.current = draft;

    rec.onresult = (event: SpeechRecognitionEvent) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? '';
        if (result.isFinal) final += text;
        else interim += text;
      }
      const base = draftAtStartRef.current;
      const combined = (base ? base + ' ' : '') + (final + interim).trim();
      setChatDraft(combined);
      if (final) draftAtStartRef.current = combined;
    };
    rec.onerror = (e) => {
      toast(`Mic: ${e.error || 'error'}`);
      setListening(false);
    };
    rec.onend = () => setListening(false);

    try {
      rec.start();
      recRef.current = rec;
      setListening(true);
      toast('Listening…');
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to start mic');
    }
  };

  return (
    <div className="flex items-center justify-between px-1 mt-2 relative">
      <div className="flex items-center gap-1">
        <button
          ref={modeBtnRef}
          onClick={() => setModeOpen((v) => !v)}
          className={cn(
            'h-7 flex items-center gap-1.5 px-2.5 rounded-full text-xs transition-colors',
            'bg-bg-panel text-fg border border-border-subtle hover:bg-bg-hover',
          )}
          title="Permission mode (Shift+Ctrl+M)"
        >
          <Lock size={11} strokeWidth={1.75} />
          <span>{currentMode.label}</span>
          <ChevronUp size={11} strokeWidth={1.75} className={cn('transition-transform', modeOpen && 'rotate-180')} />
        </button>

        {modeOpen && (
          <div
            ref={modePopupRef}
            className={cn(
              'absolute bottom-9 left-0 z-50 w-[280px] rounded-lg shadow-popup',
              'bg-bg-panel border border-border py-1',
            )}
          >
            <div className="flex items-center justify-between px-3 py-1.5 text-xs text-fg-subtle">
              <span>Mode</span>
              <div className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 rounded bg-bg-hover text-[10px] border border-border-subtle">⇧</kbd>
                <kbd className="px-1.5 py-0.5 rounded bg-bg-hover text-[10px] border border-border-subtle">Ctrl</kbd>
                <kbd className="px-1.5 py-0.5 rounded bg-bg-hover text-[10px] border border-border-subtle">M</kbd>
              </div>
            </div>
            {PERMISSION_MODES.map((m) => {
              const active = m.id === permissionMode;
              return (
                <button
                  key={m.id}
                  onClick={() => { setPermissionMode(m.id); setModeOpen(false); }}
                  className={cn(
                    'w-full flex items-center justify-between px-3 py-2 text-sm',
                    'text-fg hover:bg-bg-hover transition-colors',
                  )}
                >
                  <span>{m.label}</span>
                  <span className="flex items-center gap-2 text-fg-subtle">
                    {active && <Check size={13} strokeWidth={2} className="text-fg" />}
                    <span className="text-xs">{m.key}</span>
                  </span>
                </button>
              );
            })}
          </div>
        )}

        <IconBtn title="Attach file (CSV → dataset)" onClick={handlePlusClick}>
          <Plus size={13} strokeWidth={1.75} />
        </IconBtn>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv,text/plain,.txt,.md,.json"
          className="hidden"
          onChange={handleFileChosen}
        />
        <IconBtn
          title={listening ? 'Stop listening' : 'Voice input'}
          onClick={handleMicClick}
          active={listening}
          trailing={<ChevronDown size={10} strokeWidth={1.75} />}
        >
          <Mic size={12} strokeWidth={1.75} className={listening ? 'animate-pulse' : ''} />
        </IconBtn>
      </div>
      <ModelPicker />
    </div>
  );
}
