/**
 * Artifact-open intent detection.
 *
 * Background: when a user has already generated a report earlier in the
 * session, the LLM often won't call `render_report` again — it just
 * mentions the existing `report_id` in plain text. That means the
 * tool_result auto-open hook in `useAppStore.sendMessage` never fires,
 * and the artifacts panel stays as-is.
 *
 * This module gives us small pure helpers to:
 *  1. detect when a user message *intends* to open the artifact
 *     ("show artifact", "open report", "report dikha", direct ID, …)
 *  2. extract a `rp_<hex>` id from any free-form text
 *  3. scan a message history for the most recent report id
 *
 * Everything here is presentation-side; no network, no auth — we just
 * flip the existing `activeReportId` switch in the store, which the
 * iframe in ArtifactsPane.tsx already knows how to render.
 */

import type { Message } from './api';

/**
 * `rp_` followed by ≥6 hex chars. Backend currently emits 16, but we
 * keep the floor low so future id schemes don't silently break the
 * regex. Word boundaries on both sides avoid false positives inside
 * longer tokens.
 */
export const REPORT_ID_PATTERN = /\brp_[a-f0-9]{6,}\b/i;

/**
 * Phrases that mean "please open / show / render the (latest) report".
 * English, Hinglish and Hindi-in-Latin variants. We test against the
 * lowercased, whitespace-collapsed message — keep tokens simple.
 *
 * Intentionally permissive: false positives just open the artifacts
 * panel (which the user can ignore), false negatives leave the user
 * stuck — so we err toward opening.
 */
const OPEN_INTENT_PATTERNS: RegExp[] = [
  // English
  /\bshow\s+(the\s+)?artifact(s)?\b/,
  /\bopen\s+(the\s+)?(report|artifact)\b/,
  /\bview\s+(the\s+)?(report|artifact)\b/,
  /\brender\s+(the\s+)?(report|artifact)\b/,
  /\bdisplay\s+(the\s+)?(report|artifact)\b/,
  // Hinglish — "report dikha", "report kholo", "artifact kholo"
  /\b(report|artifact)\s+(dikh(a|ao|aao)|khol(o|do)|open\s+kar(o|do))\b/,
  /\b(dikh(a|ao|aao)|khol(o|do))\s+(the\s+)?(report|artifact)\b/,
  // "ye/yeh report open karo", "is report ko kholo"
  /\b(ye|yeh|is)\s+(report|artifact|link|html)\s+(ko\s+)?(open|khol|dikh)/,
  /\b(open|khol|dikh)\s+(karo|do|de)\b.*\b(report|artifact|html)\b/,
];

const REPORT_KEYWORD_HINTS = [
  'report', 'artifact', 'rp_', 'html', 'pdf',
];

export interface ArtifactIntent {
  /** True if the message reads as an "open the report" command. */
  open: boolean;
  /**
   * Specific report id mentioned in the message, if any. Takes
   * precedence over "latest in history" when set.
   */
  explicitId: string | null;
}

/**
 * Classify a user message for artifact-open intent.
 *
 * Rules (in order):
 *  - explicit `rp_<hex>` mention → open that one
 *  - matches any open-intent phrase → open latest
 *  - mentions a report keyword AND a verb hint we missed → fall back
 *    to false to keep the LLM in the loop
 */
export function classifyArtifactIntent(text: string): ArtifactIntent {
  const explicit = extractReportId(text);
  if (explicit) return { open: true, explicitId: explicit };

  const normalized = text.toLowerCase().replace(/\s+/g, ' ').trim();
  if (!normalized) return { open: false, explicitId: null };

  for (const re of OPEN_INTENT_PATTERNS) {
    if (re.test(normalized)) return { open: true, explicitId: null };
  }
  return { open: false, explicitId: null };
}

/** Extract the first `rp_<hex>` id from a string, or null. */
export function extractReportId(text: string): string | null {
  const m = text.match(REPORT_ID_PATTERN);
  return m ? m[0] : null;
}

/**
 * Walk a message list newest-to-oldest and return the most recent
 * `report_id` (with title if available) emitted by a tool result.
 *
 * Mirrors the inline scan that already exists in
 * `useAppStore.loadMessages`. Extracted here so the same logic can be
 * reused by the chat-input interceptor without duplication.
 */
export function findLatestReportInMessages(
  msgs: Message[],
): { id: string; title: string | null } | null {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.role !== 'tool') continue;
    for (const block of m.content) {
      if (block.type !== 'tool_result') continue;
      const raw = (block as { content?: unknown }).content;
      let parsed: unknown = raw;
      if (typeof raw === 'string') {
        try { parsed = JSON.parse(raw); } catch { /* keep as string */ }
      }
      if (parsed && typeof parsed === 'object') {
        const obj = parsed as Record<string, unknown>;
        const rid = typeof obj.report_id === 'string' ? obj.report_id : null;
        if (rid) {
          return {
            id: rid,
            title: typeof obj.title === 'string' ? obj.title : null,
          };
        }
      }
    }
  }
  return null;
}

/**
 * Cheap pre-filter: skip the more expensive intent regex pass when the
 * message has zero report-related keywords. Used by the chat-input
 * interceptor on every keystroke-triggered send.
 */
export function looksReportRelated(text: string): boolean {
  const lower = text.toLowerCase();
  return REPORT_KEYWORD_HINTS.some((kw) => lower.includes(kw));
}
