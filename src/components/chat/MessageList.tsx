import { useEffect, useRef, useCallback } from 'react';
import { FileText } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import type { Message } from '@/lib/api';
import MarkdownText from './MarkdownText';
import AgentStepper from './AgentStepper';
import { extractReportId } from '@/lib/artifactCommands';

export default function MessageList() {
  const activeSessionId = useAppStore((s) => s.activeSessionId);
  const allMessages = useAppStore((s) => s.messagesBySession);
  const allStreaming = useAppStore((s) => s.streamingBySession);
  const allDrafts = useAppStore((s) => s.streamingDraftBySession);
  const allTools = useAppStore((s) => s.streamingToolsBySession);

  const messages = activeSessionId ? allMessages[activeSessionId] ?? [] : [];
  const streaming = activeSessionId ? allStreaming[activeSessionId] ?? false : false;
  const draft = activeSessionId ? allDrafts[activeSessionId] ?? '' : '';
  const pendingTools = activeSessionId ? allTools[activeSessionId] ?? [] : [];

  const bottomRef = useRef<HTMLDivElement>(null);
  const prevSessionRef = useRef<string | null>(null);

  const doLoad = useCallback(() => {
    if (activeSessionId && activeSessionId !== prevSessionRef.current) {
      prevSessionRef.current = activeSessionId;
      useAppStore.getState().loadMessages(activeSessionId);
    }
  }, [activeSessionId]);

  useEffect(() => { doLoad(); }, [doLoad]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  });

  if (!activeSessionId) {
    return (
      <div className="flex-1 flex items-center justify-center text-fg-muted text-sm">
        Select or create a session to start chatting.
      </div>
    );
  }

  const groupedMessages: Message[][] = [];
  let currentGroup: Message[] = [];

  for (const m of messages) {
    if (currentGroup.length === 0) {
      currentGroup.push(m);
    } else {
      const lastRole = currentGroup[currentGroup.length - 1].role;
      if (m.role === 'user') {
        groupedMessages.push(currentGroup);
        currentGroup = [m];
      } else if (lastRole === 'user') {
        groupedMessages.push(currentGroup);
        currentGroup = [m];
      } else {
        currentGroup.push(m);
      }
    }
  }
  if (currentGroup.length > 0) {
    groupedMessages.push(currentGroup);
  }

  const lastGroupIndex = groupedMessages.length - 1;
  const lastGroup = lastGroupIndex >= 0 ? groupedMessages[lastGroupIndex] : null;
  const lastGroupIsUser = lastGroup ? lastGroup[0]?.role === 'user' : false;
  
  // If we are streaming and the last group is an AI turn, attach streaming state to it.
  // Otherwise (e.g. just after a user message, before first AI message is committed), we render standalone.
  const appendStreamingToLast = !lastGroupIsUser && (pendingTools.length > 0 || streaming);
  const pendingToolIds = new Set(pendingTools.map(t => t.id));

  return (
    <div className="flex-1 overflow-y-auto min-w-0">
      <div className="max-w-3xl mx-auto px-6 py-4 space-y-5">
      {groupedMessages.map((group, index) => {
        const isLast = index === lastGroupIndex;
        return (
          <MessageGroup 
            key={index} 
            messages={group} 
            pendingTools={isLast && appendStreamingToLast ? pendingTools : []}
            streaming={isLast && appendStreamingToLast ? streaming : false}
            draft={isLast && appendStreamingToLast ? draft : ''}
            pendingToolIds={pendingToolIds}
          />
        );
      })}

      {!appendStreamingToLast && (pendingTools.length > 0 || streaming) && (
        <div className="flex gap-3 min-w-0">
          <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center text-[10px] font-bold text-accent shrink-0 mt-0.5">AI</div>
          <div className="flex-1 min-w-0 space-y-2">
            {pendingTools.map((t) => (
              <div key={t.id} className="text-xs bg-bg-hover border border-border-subtle rounded-lg px-3 py-2 flex items-center gap-2">
                <span className="text-amber-400">⚡</span>
                <span className="text-accent font-medium">{t.name}</span>
                {t.result ? (
                  <span className={`ml-auto ${t.result.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                    {t.result.ok ? '✓ Done' : `✗ ${t.result.error}`}
                  </span>
                ) : (
                  <span className="text-fg-muted ml-auto animate-pulse">Running…</span>
                )}
              </div>
            ))}
            {streaming && draft && (
              <div className="text-sm text-fg">
                <MarkdownText source={draft} />
                <span className="inline-block w-1.5 h-4 bg-accent animate-pulse-dot ml-0.5" />
              </div>
            )}
            {streaming && !draft && pendingTools.length === 0 && (
              <div className="text-sm text-fg-muted"><span className="inline-block w-1.5 h-4 bg-accent animate-pulse-dot" /></div>
            )}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageGroup({ 
  messages, 
  pendingTools = [], 
  streaming = false, 
  draft = '',
  pendingToolIds = new Set() 
}: { 
  messages: Message[]; 
  pendingTools?: any[]; 
  streaming?: boolean; 
  draft?: string;
  pendingToolIds?: Set<string>;
}) {
  const isUser = messages[0]?.role === 'user';

  return (
    <div className="flex gap-3">
      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5 ${isUser ? 'bg-fg/10 text-fg-muted' : 'bg-accent/20 text-accent'}`}>
        {isUser ? 'U' : 'AI'}
      </div>
      <div className="flex-1 min-w-0 space-y-2">
        {messages.map((m, i) => (
          <MessageContent key={m.id || i} message={m} pendingToolIds={pendingToolIds} />
        ))}
        {/* Streaming elements appended seamlessly to the AI's turn */}
        {pendingTools.map((t) => (
          <div key={t.id} className="text-xs bg-bg-hover border border-border-subtle rounded-lg px-3 py-2 flex items-center gap-2">
            <span className="text-amber-400">⚡</span>
            <span className="text-accent font-medium">{t.name}</span>
            {t.result ? (
              <span className={`ml-auto ${t.result.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {t.result.ok ? '✓ Done' : `✗ ${t.result.error}`}
              </span>
            ) : (
              <span className="text-fg-muted ml-auto animate-pulse">Running…</span>
            )}
          </div>
        ))}
        {streaming && draft && (
          <div className="text-sm text-fg">
            <MarkdownText source={draft} />
            <span className="inline-block w-1.5 h-4 bg-accent animate-pulse-dot ml-0.5" />
          </div>
        )}
        {streaming && !draft && pendingTools.length === 0 && (
          <div className="text-sm text-fg-muted"><span className="inline-block w-1.5 h-4 bg-accent animate-pulse-dot" /></div>
        )}
      </div>
    </div>
  );
}

function MessageContent({ message, pendingToolIds = new Set() }: { message: Message; pendingToolIds?: Set<string> }) {
  const text = message.content
    .filter((b): b is { type: string; text: string } => b.type === 'text' && typeof b.text === 'string')
    .map((b) => b.text)
    .join('');
  const toolUses = message.content.filter((b) => b.type === 'tool_use' && !pendingToolIds.has(b.id as string));
  const toolResults = message.content.filter((b) => b.type === 'tool_result');

  // Detect a `rp_<hex>` mention in assistant text. We use this to (a)
  // auto-open the artifacts panel as a fallback when the LLM didn't
  // re-call render_report (Layer 2) and (b) render a one-click "Open in
  // Artifacts" pill the user can fire manually (Layer 3).
  const mentionedReportId =
    message.role === 'assistant' && text ? extractReportId(text) : null;

  const activeReportId = useAppStore((s) => s.activeReportId);
  const setActiveReport = useAppStore((s) => s.setActiveReport);

  // Layer 2 — only auto-flip the panel if no other report is currently
  // active. We *don't* overwrite an existing selection on every render;
  // that would yank focus from a report the user is reading.
  useEffect(() => {
    if (mentionedReportId && !activeReportId) {
      setActiveReport(mentionedReportId, null);
    }
  }, [mentionedReportId, activeReportId, setActiveReport]);

  if (message.role === 'tool') {
    return (
      <div className="space-y-1">
        {toolResults.map((tr, i) => (
          <details key={i} className="text-xs bg-bg-hover border border-border-subtle rounded-lg">
            <summary className="px-3 py-2 cursor-pointer text-fg-muted hover:text-fg">Tool result</summary>
            <div className="px-3 pb-2 font-mono text-fg-subtle whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
              {String((tr as any).content ?? '').substring(0, 500)}
            </div>
          </details>
        ))}
      </div>
    );
  }

  return (
    <>
      {text && (
        <div className="text-sm text-fg">
          <AgentStepper text={text} />
          <MarkdownText source={text} />
        </div>
      )}
      {/* Layer 3 — explicit fallback button & Share */}
      {mentionedReportId && (
        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={() => setActiveReport(mentionedReportId, null)}
            title={`Open ${mentionedReportId} in artifacts panel`}
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-accent/15 hover:bg-accent/25 text-accent border border-accent/30 transition-colors"
          >
            <FileText size={12} strokeWidth={2} />
            Open in Artifacts
          </button>
          <button
            onClick={() => {
              const shareText = `Check out my new algorithmic trading strategy! Generated with StratForge AI.\nReport ID: ${mentionedReportId}`;
              navigator.clipboard.writeText(shareText);
            }}
            title="Copy Share Text"
            className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-[#24A1DE]/15 hover:bg-[#24A1DE]/25 text-[#24A1DE] border border-[#24A1DE]/30 transition-colors"
          >
            {/* Share Icon placeholder, using text since lucide icon might not be imported yet */}
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
            Share
          </button>
        </div>
      )}
      {toolUses.map((tu, i) => (
        <div key={i} className="text-xs bg-bg-hover border border-border-subtle rounded-lg px-3 py-2 flex items-center gap-2">
          <span className="text-amber-400">⚡</span>
          <span className="text-accent font-medium">{String(tu.name)}</span>
          <span className="text-fg-subtle truncate">{JSON.stringify(tu.input).substring(0, 80)}</span>
        </div>
      ))}
    </>
  );
}
