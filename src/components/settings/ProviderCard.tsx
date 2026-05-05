import { useState } from 'react';
import { cn } from '@/lib/cn';
import type { ProviderInfo, ProviderKind } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { toast } from '../ui/Toast';
import Tooltip from '../ui/Tooltip';
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
  const isClaudeCli = provider.name === 'claude-cli';
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
    if (isClaudeCli) {
      if (provider.reachable === true) return 'CLI detected — logged in';
      if (provider.extra?.cli_installed) return 'CLI installed but missing auth (run: claude login)';
      return 'CLI not found (install via npm)';
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
            {isClaudeCli ? (
              <div className="text-xs text-fg-muted mt-1 flex items-center gap-1.5 flex-wrap">
                <span>Use your Claude Code CLI login to access Claude models.</span>
                <Tooltip 
                  position="bottom"
                  contentClassName="!max-w-[420px]"
                  content={
                    <div className="space-y-3 py-1 text-[11px]">
                      <div>
                        <p className="font-semibold text-fg">Step 1: Command Kahan Run Karni Hai?</p>
                        <p className="text-fg-subtle mt-0.5">Apne computer par naya Command Prompt, PowerShell ya VS Code Terminal open karein. Wahan type karein: <code className="bg-white/10 px-1 py-0.5 rounded text-[10px]">claude login</code> aur Enter press karein.</p>
                      </div>
                      <div>
                        <p className="font-semibold text-fg">Step 2: CLI Mein Login Kaise Hoga?</p>
                        <ul className="list-disc list-outside ml-3.5 mt-0.5 space-y-0.5 text-fg-subtle">
                          <li>Browser automatically open ho jayega. (Agar na ho toh terminal se link copy kar ke khol lein).</li>
                          <li>Apne Claude account (Google/Email) se login karein.</li>
                          <li>Browser mein <i>"Login Successful - You can close this tab"</i> aane ke baad tab close kar dein.</li>
                        </ul>
                      </div>
                      <div>
                        <p className="font-semibold text-fg">Step 3: CLI aur App Connect Kaise Honge?</p>
                        <p className="text-fg-subtle mt-0.5">Aapko khud kuch nahi karna, yeh <b>completely automatic</b> hai! CLI ek hidden <code className="bg-white/10 px-1 py-0.5 rounded text-[10px]">auth.json</code> file save karegi jise StratForge detect kar lega. Settings refresh karne par card <b>Green (✓ Connected)</b> ho jayega.</p>
                      </div>
                      <div>
                        <p className="font-semibold text-fg">Step 4: Use Kaise Karein?</p>
                        <p className="text-fg-subtle mt-0.5">Chat interface par jayen, top se <b>Model Picker</b> open karein, aur list se <b>Claude 3.5 Sonnet (CLI)</b> select kar ke chat start karein!</p>
                      </div>
                    </div>
                  }
                >
                  <span className="text-accent hover:text-accent-hover transition-colors">How to connect?</span>
                </Tooltip>
              </div>
            ) : (
              <p className="text-xs text-fg-muted mt-1">{description}</p>
            )}
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
            {configured && !isOllama && !isChatGPT && !isClaudeCli && (
              <button
                onClick={handleDisconnect}
                className="h-7 px-2.5 text-xs rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
              >
                Disconnect
              </button>
            )}
            {!isClaudeCli && (
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
            )}
            {isClaudeCli && (
              <span className={cn(
                'h-7 px-3 text-xs rounded flex items-center',
                configured ? 'text-emerald-400' : 'text-amber-400',
              )}>
                {configured ? '✓ Connected' : '✗ Not Connected'}
              </span>
            )}
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
