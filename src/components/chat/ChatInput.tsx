import { useEffect, useRef } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useActiveSession, useAppStore } from '@/store/useAppStore';

export default function ChatInput() {
  const session = useActiveSession();
  const streaming = useAppStore((s) =>
    session ? s.streamingBySession[session.id] ?? false : false,
  );
  const sendMessage = useAppStore((s) => s.sendMessage);
  const cancelStream = useAppStore((s) => s.cancelStream);
  const value = useAppStore((s) => s.chatDraft);
  const setValue = useAppStore((s) => s.setChatDraft);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const disabled = !session;
  const lastMessage = session?.messages?.[session.messages.length - 1];
  const hasError = lastMessage?.content?.includes('❌ Error') || 
                   lastMessage?.content?.includes('❌ Backtest failed') ||
                   lastMessage?.content?.includes('failed:');

  const autosize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  // Re-autosize when draft is updated externally (mic/attach).
  useEffect(() => { autosize(); }, [value]);

  const handleSend = () => {
    const text = value.trim();
    if (!text || !session) return;
    sendMessage(session.id, text);
    setValue('');
    if (taRef.current) {
      taRef.current.style.height = 'auto';
    }
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {/* Smart Alerts & Auto-Fix Quick Action */}
      {!streaming && lastMessage?.role === 'assistant' && hasError && (
        <div className="flex px-1">
          <button
            onClick={() => {
              sendMessage(session!.id, 'Fix this error automatically.');
            }}
            className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 transition-colors"
          >
            <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
            Fix this automatically
          </button>
        </div>
      )}

      <div
        className={cn(
          'relative bg-bg-panel border border-border-subtle rounded-pill',
        'focus-within:border-border transition-colors',
        disabled && 'opacity-60',
      )}
    >
      <textarea
        ref={taRef}
        value={value}
        onChange={(e) => { setValue(e.target.value); }}
        onKeyDown={handleKey}
        placeholder={disabled ? 'Select or create a session to start…' : 'Type a message…'}
        disabled={disabled || streaming}
        rows={1}
        className={cn(
          'w-full resize-none bg-transparent outline-none px-5 py-4 pr-14',
          'text-sm placeholder:text-fg-subtle disabled:cursor-not-allowed',
        )}
      />
      <div className="absolute right-3 bottom-3">
        {streaming ? (
          <button
            onClick={() => session && cancelStream(session.id)}
            title="Stop"
            className={cn(
              'h-8 w-8 flex items-center justify-center rounded-lg',
              'bg-bg-hover text-fg hover:bg-border-strong transition-colors',
            )}
          >
            <Square size={12} strokeWidth={2} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            title="Send"
            className={cn(
              'h-8 w-8 flex items-center justify-center rounded-lg',
              'bg-accent hover:bg-accent-hover text-white',
              'disabled:opacity-30 disabled:cursor-not-allowed transition-colors',
            )}
          >
            <ArrowUp size={14} strokeWidth={2} />
          </button>
        )}
      </div>
      </div>
    </div>
  );
}
