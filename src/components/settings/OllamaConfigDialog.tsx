import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { ProviderInfo } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { toast } from '../ui/Toast';

interface Props {
  provider: ProviderInfo;
  onClose: () => void;
}

export default function OllamaConfigDialog({ provider, onClose }: Props) {
  const updateBaseUrl = useAppStore((s) => s.updateOllamaBaseUrl);
  const refresh = useAppStore((s) => s.refreshProviders);

  const initialUrl =
    (provider.extra?.base_url as string | undefined) ??
    (provider.extra?.default_base_url as string | undefined) ??
    'http://localhost:11434';
  const defaultUrl =
    (provider.extra?.default_base_url as string | undefined) ??
    'http://localhost:11434';

  const [value, setValue] = useState(initialUrl);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await updateBaseUrl(trimmed);
      // Re-ping so reachability dot reflects the new URL.
      await refresh();
      toast('Ollama base URL saved');
      onClose();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to save');
      setBusy(false);
    }
  };

  return (
    <div
      data-settings-dialog="true"
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-bg-panel border border-border-subtle rounded-xl shadow-popup"
      >
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-border-subtle">
          <div>
            <h2 className="text-sm font-medium">Configure Ollama</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              Point StratForge at a running Ollama daemon (local or remote).
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover"
          >
            <X size={14} strokeWidth={1.75} />
          </button>
        </header>

        <div className="px-5 py-4">
          <label className="block text-xs font-medium text-fg-muted mb-1.5">
            Base URL
          </label>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy) handleSave();
            }}
            placeholder={defaultUrl}
            className={cn(
              'w-full px-3 py-2 rounded bg-bg border border-border',
              'text-sm font-mono text-fg placeholder:text-fg-faint',
              'focus:outline-none focus:border-border-strong',
            )}
          />
          <p className="text-[11px] text-fg-subtle mt-2">
            Default: <span className="font-mono">{defaultUrl}</span>. Install
            Ollama from ollama.com and run <span className="font-mono">ollama serve</span>.
          </p>
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-subtle">
          <button
            onClick={() => setValue(defaultUrl)}
            disabled={busy}
            className="h-8 px-3 text-xs rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors mr-auto"
          >
            Reset to default
          </button>
          <button
            onClick={onClose}
            disabled={busy}
            className="h-8 px-3 text-xs rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={busy || !value.trim()}
            className={cn(
              'h-8 px-4 text-xs rounded font-medium transition-colors',
              'bg-accent hover:bg-accent-hover text-white',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </footer>
      </div>
    </div>
  );
}
