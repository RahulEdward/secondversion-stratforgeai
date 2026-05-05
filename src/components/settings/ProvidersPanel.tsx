import { useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import type { ProviderInfo, ProviderKind } from '@/lib/api';
import ProviderCard from './ProviderCard';

interface PlaceholderProvider {
  name: string;
  label: string;
  kind: ProviderKind;
  comingPhase: string;
  description: string;
}

// No placeholders — ChatGPT subscription is a real provider from the backend.
const PLACEHOLDERS: PlaceholderProvider[] = [];

const DESCRIPTIONS: Record<string, string> = {
  anthropic:
    'Use your own Anthropic API key for Claude models (Opus, Sonnet, Haiku).',
  openai:
    'Use your own OpenAI API key for GPT-4, GPT-5, o1, o3, and o4 models.',
  google:
    'Use your own Google AI Studio API key for Gemini models.',
  ollama:
    'Run open-source models locally via Ollama. No API key — just a base URL.',
  'chatgpt-subscription':
    'Sign in with your ChatGPT Plus/Pro/Team subscription to access GPT-5 models at no extra API cost.',
  'claude-cli':
    'Use your Claude Code CLI login (Free/Pro/Max plan) to access Claude models at no extra API cost. Requires the Claude CLI installed and logged in.',
};

export default function ProvidersPanel() {
  const providers = useAppStore((s) => s.providers);
  const loading = useAppStore((s) => s.providersLoading);
  const refresh = useAppStore((s) => s.refreshProviders);

  useEffect(() => {
    if (providers.length === 0) refresh();
  }, [providers.length, refresh]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-8 py-8">
        <header className="mb-6">
          <h1 className="text-lg font-semibold">Providers</h1>
          <p className="text-sm text-fg-muted mt-1">
            Configure how StratForge talks to language models. Keys are stored
            in your OS keychain and never leave this machine.
          </p>
        </header>

        {loading && providers.length === 0 ? (
          <div className="text-sm text-fg-muted">Loading providers…</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {providers.map((p: ProviderInfo) => (
              <ProviderCard
                key={p.name}
                provider={p}
                description={DESCRIPTIONS[p.name] ?? ''}
              />
            ))}
            {PLACEHOLDERS.map((p) => (
              <ProviderCard
                key={p.name}
                placeholder={p}
                description={p.description}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
