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

// Voice input handled via MediaRecorder and backend /api/agent/transcribe.

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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [listening, setListening] = useState(false);
  const [modeOpen, setModeOpen] = useState(false);
  const modeBtnRef = useRef<HTMLButtonElement>(null);
  const modePopupRef = useRef<HTMLDivElement>(null);

  const currentMode = PERMISSION_MODES.find((m) => m.id === permissionMode) ?? PERMISSION_MODES[1];

  // Cleanup mic on unmount.
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current) {
        try {
          mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
        } catch { /* noop */ }
      }
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

  // ── Mic button: MediaRecorder toggle ──
  const handleMicClick = async () => {
    if (listening) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
      }
      return; // setListening(false) is called in onstop
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        setListening(false);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (audioBlob.size === 0) return;

        toast('Transcribing...');
        try {
          const { transcribeAudio } = await import('@/lib/api');
          const text = await transcribeAudio(audioBlob);
          if (text) {
            const currentDraft = useAppStore.getState().chatDraft;
            setChatDraft((currentDraft ? currentDraft + ' ' : '') + text.trim());
            toast('Transcription added');
          } else {
            toast('No speech detected');
          }
        } catch (err) {
          let msg = 'Transcription failed';
          if (err instanceof Error) {
            msg = err.message;
            try {
              const parsed = JSON.parse(msg);
              if (parsed && typeof parsed === 'object' && parsed.detail) {
                msg = parsed.detail;
              }
            } catch { /* ignore parse error */ }
          }
          toast(msg);
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setListening(true);
      toast('Listening… (Click again to stop)');
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
