import { useEffect, useRef, useState } from 'react';
import { Copy, ExternalLink, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { ProviderInfo } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { toast } from '../ui/Toast';

interface Props {
  provider: ProviderInfo;
  onClose: () => void;
}

type Phase = 'idle' | 'launching' | 'waiting' | 'success' | 'error';

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

export default function ChatGPTLoginDialog({ provider, onClose }: Props) {
  const startAuth = useAppStore((s) => s.startChatGPTAuth);
  const pollAuth = useAppStore((s) => s.pollChatGPTAuth);
  const signOut = useAppStore((s) => s.signOutChatGPT);
  const refresh = useAppStore((s) => s.refreshProviders);

  const [phase, setPhase] = useState<Phase>('idle');
  const [authorizeUrl, setAuthorizeUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAtRef = useRef<number>(0);
  const cancelledRef = useRef<boolean>(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); handleClose(); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  const handleClose = () => {
    cancelledRef.current = true;
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    onClose();
  };

  const schedulePoll = (flowId: string) => {
    if (cancelledRef.current) return;
    if (Date.now() - startedAtRef.current > POLL_TIMEOUT_MS) {
      setErrorMsg('Sign-in timed out. Please try again.');
      setPhase('error');
      return;
    }
    pollTimerRef.current = setTimeout(() => void runPoll(flowId), POLL_INTERVAL_MS);
  };

  const runPoll = async (flowId: string) => {
    if (cancelledRef.current) return;
    try {
      const status = await pollAuth(flowId);
      if (cancelledRef.current) return;
      if (status.status === 'pending') { schedulePoll(flowId); return; }
      if (status.status === 'complete') {
        setPhase('success');
        await refresh();
        toast('ChatGPT subscription connected');
        setTimeout(() => { if (!cancelledRef.current) onClose(); }, 900);
        return;
      }
      if (status.status === 'expired') {
        setErrorMsg('Sign-in expired. Please try again.');
        setPhase('error');
        return;
      }
      setErrorMsg(status.error || 'Sign-in failed');
      setPhase('error');
    } catch {
      if (!cancelledRef.current) schedulePoll(flowId);
    }
  };

  const handleStart = async () => {
    setBusy(true);
    setErrorMsg(null);
    setPhase('launching');
    try {
      const { flow_id, authorize_url } = await startAuth();
      setAuthorizeUrl(authorize_url);
      startedAtRef.current = Date.now();
      cancelledRef.current = false;
      window.open(authorize_url, '_blank', 'noopener,noreferrer');
      setPhase('waiting');
      schedulePoll(flow_id);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to start sign-in');
      setPhase('error');
    } finally {
      setBusy(false);
    }
  };

  const handleSignOut = async () => {
    setBusy(true);
    try {
      await signOut();
      toast('Signed out of ChatGPT');
      onClose();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to sign out');
      setBusy(false);
    }
  };

  const signedIn = provider.has_credential;
  const email = (provider.extra?.email as string | undefined) ?? '';

  return (
    <div
      data-settings-dialog="true"
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4"
      onClick={handleClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-bg-panel border border-border-subtle rounded-xl shadow-popup"
      >
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-border-subtle">
          <div>
            <h2 className="text-sm font-medium">
              {signedIn ? 'ChatGPT subscription' : 'Sign in with ChatGPT'}
            </h2>
            <p className="text-xs text-fg-muted mt-0.5">
              {signedIn
                ? 'Use your ChatGPT Plus/Pro/Team plan at no extra API cost.'
                : 'Connect your ChatGPT subscription — no API key needed.'}
            </p>
          </div>
          <button onClick={handleClose} className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover">
            <X size={14} strokeWidth={1.75} />
          </button>
        </header>

        <div className="px-5 py-4 min-h-[120px]">
          {signedIn && phase === 'idle' && (
            <div className="flex items-start gap-3">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-2 shrink-0" />
              <div className="text-xs text-fg-muted leading-relaxed">
                {email ? (<>Signed in as <span className="text-fg">{email}</span>. </>) : (<>You're signed in. </>)}
                Tokens are stored locally. Sign out to disconnect.
              </div>
            </div>
          )}

          {!signedIn && phase === 'idle' && (
            <ol className="text-xs text-fg-muted space-y-2 list-decimal list-inside leading-relaxed">
              <li>Click <span className="text-fg">Sign in with ChatGPT</span> below.</li>
              <li>Your browser opens the OpenAI login page.</li>
              <li>After you approve, control returns here automatically.</li>
            </ol>
          )}

          {(phase === 'launching' || phase === 'waiting') && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs text-fg">
                <Loader2 size={14} className="animate-spin text-accent" />
                <span>{phase === 'launching' ? 'Opening browser…' : 'Waiting for sign-in…'}</span>
              </div>
              {authorizeUrl && (
                <div className="flex items-center gap-2">
                  <button onClick={() => window.open(authorizeUrl, '_blank', 'noopener,noreferrer')}
                    className="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11px] rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors">
                    <ExternalLink size={12} strokeWidth={1.75} /> Re-open browser
                  </button>
                  <button onClick={async () => { try { await navigator.clipboard.writeText(authorizeUrl); toast('URL copied'); } catch { toast('Copy failed'); } }}
                    className="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11px] rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors">
                    <Copy size={12} strokeWidth={1.75} /> Copy URL
                  </button>
                </div>
              )}
            </div>
          )}

          {phase === 'success' && (
            <div className="flex items-center gap-2 text-xs text-emerald-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>Signed in. You can now select GPT-5 models.</span>
            </div>
          )}

          {phase === 'error' && (
            <div className="space-y-2">
              <div className="flex items-start gap-2 text-xs text-red-300">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 mt-1.5 shrink-0" />
                <span className="break-words">{errorMsg ?? 'Sign-in failed'}</span>
              </div>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-subtle">
          {signedIn && phase === 'idle' && (
            <button onClick={handleSignOut} disabled={busy}
              className={cn('h-8 px-3 text-xs rounded font-medium transition-colors mr-auto', 'text-red-300 hover:text-red-200 hover:bg-red-500/10', 'disabled:opacity-40 disabled:cursor-not-allowed')}>
              {busy ? 'Signing out…' : 'Sign out'}
            </button>
          )}
          <button onClick={handleClose} disabled={busy && phase !== 'waiting'}
            className="h-8 px-3 text-xs rounded text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors">
            {phase === 'waiting' ? 'Cancel' : 'Close'}
          </button>
          {!signedIn && (phase === 'idle' || phase === 'error') && (
            <button onClick={handleStart} disabled={busy}
              className={cn('h-8 px-4 text-xs rounded font-medium transition-colors', 'bg-accent hover:bg-accent-hover text-white', 'disabled:opacity-40 disabled:cursor-not-allowed')}>
              {phase === 'error' ? 'Try again' : 'Sign in with ChatGPT'}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
