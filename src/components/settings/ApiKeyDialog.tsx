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

export default function ApiKeyDialog({ provider, onClose }: Props) {
  const saveKey = useAppStore((s) => s.saveProviderKey);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
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
      await saveKey(provider.name, trimmed);
      toast(`${provider.label} key saved`);
      onClose();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to save key');
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
            <h2 className="text-sm font-medium">Connect {provider.label}</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              Your key is stored in the OS keychain and never leaves this machine.
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
            API key
          </label>
          <input
            ref={inputRef}
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy) handleSave();
            }}
            placeholder={placeholderFor(provider.name)}
            className={cn(
              'w-full px-3 py-2 rounded bg-bg border border-border',
              'text-sm font-mono text-fg placeholder:text-fg-faint',
              'focus:outline-none focus:border-border-strong',
            )}
          />
          <p className="text-[11px] text-fg-subtle mt-2">{hintFor(provider.name)}</p>
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-subtle">
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
            {busy ? 'Saving…' : 'Save key'}
          </button>
        </footer>
      </div>
    </div>
  );
}

function placeholderFor(name: string): string {
  switch (name) {
    case 'anthropic':
      return 'sk-ant-…';
    case 'openai':
      return 'sk-…';
    case 'google':
      return 'AIza…';
    default:
      return 'Paste your API key';
  }
}

function hintFor(name: string): string {
  switch (name) {
    case 'anthropic':
      return 'Get your key at console.anthropic.com → Settings → API keys.';
    case 'openai':
      return 'Get your key at platform.openai.com → API keys.';
    case 'google':
      return 'Get your key at aistudio.google.com → Get API key.';
    default:
      return '';
  }
}
