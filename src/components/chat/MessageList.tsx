import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import type { Message } from '@/lib/api';
import MarkdownText from './MarkdownText';
import ToolActivity, { type ToolActivityItem } from './ToolActivity';
import ReportCard from './ReportCard';
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
            {pendingTools.length > 0 && (
              <ToolActivity items={pendingTools as ToolActivityItem[]} streaming={streaming} />
            )}
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
        {/* Streaming tools — collapsed into a single expandable summary row */}
        {pendingTools.length > 0 && (
          <ToolActivity items={pendingTools as ToolActivityItem[]} streaming={streaming} />
        )}
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

  // Detect a `rp_<hex>` mention in assistant text so we can render an
  // inline ReportCard. We do NOT auto-open the Artifacts or Preview
  // panels — the ReportCard has its own "View Full Report" button that
  // the user clicks explicitly.
  const mentionedReportId =
    message.role === 'assistant' && text ? extractReportId(text) : null;

  const activeReportId = useAppStore((s) => s.activeReportId);
  const setActiveReport = useAppStore((s) => s.setActiveReport);
  // `autoOpenedRef` kept for backward compatibility but no longer used —
  // the ReportCard now owns the "open full report" action entirely.

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
          <MarkdownText source={text} />
        </div>
      )}
      {/* Inline Report Card — shows metrics preview + "View Full Report" button */}
      {mentionedReportId && (
        <ReportCard reportId={mentionedReportId} />
      )}
      {toolUses.length > 0 && (
        <ToolActivity
          items={toolUses.map((tu, i) => ({
            id: String(tu.id ?? `${i}`),
            name: String(tu.name ?? ''),
            input: (tu.input as Record<string, unknown>) ?? {},
            result: undefined,
          }))}
          streaming={false}
        />
      )}
    </>
  );
}
