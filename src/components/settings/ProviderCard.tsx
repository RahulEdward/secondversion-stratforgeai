import { useState } from 'react';
import { cn } from '@/lib/cn';
import type { ProviderInfo, ProviderKind } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { toast } from '../ui/Toast';
import ApiKeyDialog from './ApiKeyDialog';
import ChatGPTLoginDialog from './ChatGPTLoginDialog';
import OllamaConfigDialog from './OllamaConfigDialog';

interface PlaceholderProvider {
  name: string;
  label: string;
  kind: ProviderKind;
  comingPhase: string;
}

interface Props {
  provider?: ProviderInfo;
  placeholder?: PlaceholderProvider;
  description: string;
}

const KIND_STYLES: Record<
  ProviderKind,
  { label: string; className: string }
> = {
  api_key: {
    label: 'API key',
    className: 'bg-blue-500/10 text-blue-300 border border-blue-500/20',
  },
  local: {
    label: 'Local',
    className: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20',
  },
  subscription: {
    label: 'Subscription',
    className: 'bg-amber-500/10 text-amber-300 border border-amber-500/20',
  },
};

function ProviderLogo({
  name,
  placeholder,
}: {
  name: string;
  placeholder?: boolean;
}) {
  const initial = name.charAt(0).toUpperCase();
  return (
    <div
      className={cn(
        'w-9 h-9 rounded-md border flex items-center justify-center text-sm font-semibold shrink-0',
        placeholder
          ? 'bg-white/5 border-white/10 text-fg-subtle'
          : 'bg-white/10 border-white/15 text-fg',
      )}
    >
      {initial}
    </div>
  );
}

export default function ProviderCard({
  provider,
  placeholder,
  description,
}: Props) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const deleteKey = useAppStore((s) => s.deleteProviderKey);

  if (placeholder) {
    const kind = KIND_STYLES[placeholder.kind];
    return (
      <article
        className={cn(
          'flex flex-col gap-3 p-4 rounded-xl border border-border-subtle',
          'bg-bg-sidebar opacity-70',
        )}
      >
        <div className="flex items-start gap-3">
          <ProviderLogo name={placeholder.label} placeholder />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-medium">{placeholder.label}</h3>
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded', kind.className)}>
                {kind.label}
              </span>
            </div>
            <p className="text-xs text-fg-muted mt-1">{description}</p>
          </div>
        </div>
        <div className="flex items-center justify-between mt-auto">
          <span className="text-xs text-fg-subtle">{placeholder.comingPhase}</span>
          <button
            disabled
            className="h-7 px-3 text-xs rounded bg-white/5 text-fg-subtle cursor-not-allowed"
            title="Coming in Phase 5"
          >
            Coming soon
          </button>
        </div>
      </article>
    );
  }

  if (!provider) return null;

  const kind = KIND_STYLES[provider.kind];
  const isOllama = provider.name === 'ollama';
  const isChatGPT = provider.name === 'chatgpt-subscription';
  const configured = provider.has_credential;
  // For Ollama, configured is always true (base URL defaults), so use reachability as the status signal.
  const dotClass = (() => {
    if (isOllama) {
      if (provider.reachable === true) return 'bg-emerald-400';
      if (provider.reachable === false) return 'bg-amber-400';
      return 'bg-fg-faint';
    }
    return configured ? 'bg-emerald-400' : 'bg-fg-faint';
  })();

  const statusText = (() => {
    if (isOllama) {
      if (provider.reachable === true) return 'Daemon reachable';
      if (provider.reachable === false) return 'Daemon not running';
      return 'Unknown';
    }
    if (isChatGPT && configured) {
      const email = typeof provider.extra?.email === 'string' ? provider.extra.email : '';
      return email ? `Signed in as ${email}` : 'Signed in';
    }
    if (isChatGPT) return 'Not signed in';
    return configured ? 'Configured' : 'Not configured';
  })();

  const handleDisconnect = async () => {
    try {
      await deleteKey(provider.name);
      toast(`${provider.label} disconnected`);
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to disconnect');
    }
  };

  return (
    <>
      <article
        className={cn(
          'flex flex-col gap-3 p-4 rounded-xl border border-border-subtle',
          'bg-bg-sidebar hover:bg-bg-hover transition-colors',
        )}
      >
        <div className="flex items-start gap-3">
          <ProviderLogo name={provider.label} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-medium">{provider.label}</h3>
              <span className={cn('text-[10px] px-1.5 py-0.5 rounded', kind.className)}>
                {kind.label}
              </span>
            </div>
            <p className="text-xs text-fg-muted mt-1">{description}</p>
            {isOllama && provider.extra?.base_url && (
              <p className="text-[11px] font-mono text-fg-subtle mt-1.5 truncate">
                {String(provider.extra.base_url)}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between mt-auto pt-1">
          <div className="flex items-center gap-1.5 text-xs text-fg-muted">
            <span className={cn('w-1.5 h-1.5 rounded-full', dotClass)} />
            <span>{statusText}</span>
          </div>
          <div className="flex items-center gap-2">
            {configured && !isOllama && !isChatGPT && (
              <button
                onClick={handleDisconnect}
                className="h-7 px-2.5 text-xs rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
              >
                Disconnect
              </button>
            )}
            <button
              onClick={() => setDialogOpen(true)}
              className={cn(
                'h-7 px-3 text-xs rounded transition-colors',
                'bg-accent hover:bg-accent-hover text-white',
              )}
            >
              {isOllama
                ? 'Configure'
                : isChatGPT
                  ? configured ? 'Manage' : 'Sign in'
                  : configured
                    ? 'Update key'
                    : 'Add key'}
            </button>
          </div>
        </div>
      </article>

      {dialogOpen && !isOllama && !isChatGPT && (
        <ApiKeyDialog
          provider={provider}
          onClose={() => setDialogOpen(false)}
        />
      )}
      {dialogOpen && isOllama && (
        <OllamaConfigDialog
          provider={provider}
          onClose={() => setDialogOpen(false)}
        />
      )}
      {dialogOpen && isChatGPT && (
        <ChatGPTLoginDialog
          provider={provider}
          onClose={() => setDialogOpen(false)}
        />
      )}
    </>
  );
}
