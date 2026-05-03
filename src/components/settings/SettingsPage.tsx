import { useEffect } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import SettingsNav from './SettingsNav';
import ProvidersPanel from './ProvidersPanel';
import MemoryPanel from './MemoryPanel';

export default function SettingsPage() {
  const section = useAppStore((s) => s.settingsSection);
  const close = useAppStore((s) => s.closeSettings);

  // Close on Escape — but only if no dialog is on top (dialogs swallow Esc themselves).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        const hasDialog = document.querySelector('[data-settings-dialog="true"]');
        if (!hasDialog) close();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [close]);

  return (
    <div
      className="fixed inset-0 z-40 bg-bg flex flex-col text-fg"
      role="dialog"
      aria-modal="true"
    >
      <header className="flex items-center justify-between px-5 py-3 border-b border-border bg-bg-sidebar">
        <div className="flex items-center gap-2">
          <button
            onClick={close}
            className="flex items-center gap-1.5 h-7 px-2 -ml-1.5 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
            title="Back"
          >
            <ArrowLeft size={14} strokeWidth={1.75} />
            <span className="text-xs">Back</span>
          </button>
          <span className="text-fg-faint">·</span>
          <span className="text-sm font-medium">StratForge AI · Settings</span>
        </div>
        <button
          onClick={close}
          className="p-1.5 rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
          title="Close settings (Esc)"
        >
          <X size={16} strokeWidth={1.75} />
        </button>
      </header>

      <div className="flex flex-1 min-h-0">
        <SettingsNav />
        <main className="flex-1 flex flex-col min-w-0">
          {section === 'providers' && <ProvidersPanel />}
          {section === 'memory' && <MemoryPanel />}
          {section !== 'providers' && section !== 'memory' && (
            <div className="flex-1 flex items-center justify-center text-sm text-fg-muted">
              This section is coming in a later phase.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
