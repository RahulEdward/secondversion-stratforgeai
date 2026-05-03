import { useMemo, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import css from 'highlight.js/lib/languages/css';
import diff from 'highlight.js/lib/languages/diff';
import go from 'highlight.js/lib/languages/go';
import ini from 'highlight.js/lib/languages/ini';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import plaintext from 'highlight.js/lib/languages/plaintext';
import python from 'highlight.js/lib/languages/python';
import rust from 'highlight.js/lib/languages/rust';
import shell from 'highlight.js/lib/languages/shell';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';
import { cn } from '@/lib/cn';
import Tooltip from '../ui/Tooltip';

const TOOLTIPS: Record<string, string> = {
  'Sharpe': 'Measures risk-adjusted return. >1 is good, >2 is excellent.',
  'Sortino': 'Similar to Sharpe, but only penalizes downside volatility.',
  'Profit Factor': 'Gross profits divided by gross losses. >1.5 is strong.',
  'Max Drawdown': 'The largest peak-to-trough drop in equity. Lower is better.',
  'Maximum Drawdown': 'The largest peak-to-trough drop in equity. Lower is better.',
  'Walk-Forward Efficiency': 'Measures if a strategy overfits. >0.5 suggests robustness.',
  'MC Survival Rate': 'Probability of not hitting your drawdown limit in Monte Carlo.',
  'Win Rate': 'Percentage of trades that were profitable.',
  'p-value': 'Probability that the strategy returns are due to random chance. <0.05 is statistically significant.',
};

function withTooltips(text: string): React.ReactNode {
  const terms = Object.keys(TOOLTIPS);
  const regex = new RegExp(`\\b(${terms.join('|')})\\b`, 'g');
  
  const parts: React.ReactNode[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIdx) parts.push(text.slice(lastIdx, m.index));
    const termMatch = m[1];
    const dictKey = terms.find(t => t === termMatch) || terms.find(t => t.toLowerCase() === termMatch.toLowerCase());
    if (dictKey && TOOLTIPS[dictKey]) {
      parts.push(
        <Tooltip key={`tt${key++}`} content={TOOLTIPS[dictKey]}>
          {termMatch}
        </Tooltip>
      );
    } else {
      parts.push(termMatch);
    }
    lastIdx = m.index + termMatch.length;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  
  return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : parts;
}

hljs.registerLanguage('bash', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('shell', shell);
hljs.registerLanguage('css', css);
hljs.registerLanguage('diff', diff);
hljs.registerLanguage('go', go);
hljs.registerLanguage('ini', ini);
hljs.registerLanguage('toml', ini);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('jsx', javascript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('md', markdown);
hljs.registerLanguage('plaintext', plaintext);
hljs.registerLanguage('text', plaintext);
hljs.registerLanguage('python', python);
hljs.registerLanguage('py', python);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('rs', rust);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('tsx', typescript);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('yml', yaml);

/**
 * Lightweight Markdown renderer — fenced code blocks (with syntax
 * highlighting via highlight.js), GFM tables, inline code, bold,
 * italic, strikethrough, headers, ordered + unordered lists.
 */

type Align = 'left' | 'center' | 'right';

type Block =
  | { kind: 'p'; text: string }
  | { kind: 'h'; level: 2 | 3 | 4; text: string }
  | { kind: 'code'; lang: string; code: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'hr' }
  | { kind: 'table'; head: string[]; aligns: Align[]; rows: string[][] };

function isTableSep(line: string): boolean {
  if (!/\|/.test(line)) return false;
  const cells = splitRow(line);
  if (cells.length === 0) return false;
  return cells.every((c) => /^:?-{3,}:?$/.test(c.trim()));
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
}

function alignsFromSep(sep: string): Align[] {
  return splitRow(sep).map((c) => {
    const t = c.trim();
    const left = t.startsWith(':');
    const right = t.endsWith(':');
    if (left && right) return 'center';
    if (right) return 'right';
    return 'left';
  });
}

function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  const out: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    const fence = /^```(\w*)\s*$/.exec(line);
    if (fence) {
      const lang = fence[1] || '';
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        buf.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      out.push({ kind: 'code', lang, code: buf.join('\n') });
      continue;
    }

    // GFM table — `| h1 | h2 |` then `|---|---|` then rows
    if (
      /\|/.test(line) &&
      i + 1 < lines.length &&
      isTableSep(lines[i + 1])
    ) {
      const head = splitRow(line);
      const seps = alignsFromSep(lines[i + 1]);
      const aligns: Align[] = head.map((_, idx) => seps[idx] ?? 'left');
      i += 2;
      const rows: string[][] = [];
      while (
        i < lines.length &&
        lines[i].trim() !== '' &&
        /\|/.test(lines[i])
      ) {
        const cells = splitRow(lines[i]);
        while (cells.length < head.length) cells.push('');
        rows.push(cells.slice(0, head.length));
        i++;
      }
      out.push({ kind: 'table', head, aligns, rows });
      continue;
    }

    // Horizontal rule
    if (/^\s*---+\s*$/.test(line)) {
      out.push({ kind: 'hr' });
      i++;
      continue;
    }

    // Headers
    const h = /^(#{2,4})\s+(.+)$/.exec(line);
    if (h) {
      out.push({ kind: 'h', level: h[1].length as 2 | 3 | 4, text: h[2] });
      i++;
      continue;
    }

    // Lists
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i++;
      }
      out.push({ kind: 'ul', items });
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      out.push({ kind: 'ol', items });
      continue;
    }

    // Blank line — paragraph break
    if (line.trim() === '') {
      i++;
      continue;
    }

    // Paragraph — gather contiguous non-table-non-block lines
    const buf: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^```/.test(lines[i]) &&
      !/^(#{2,4})\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !/^\s*---+\s*$/.test(lines[i]) &&
      !(
        /\|/.test(lines[i]) &&
        i + 1 < lines.length &&
        isTableSep(lines[i + 1])
      )
    ) {
      buf.push(lines[i]);
      i++;
    }
    out.push({ kind: 'p', text: buf.join('\n') });
  }

  return out;
}

/** Inline formatting: **bold**, *italic*, ~~strike~~, `code`, [link](url),
 *  bare URLs (https://… auto-linked), and GFM task-list checkboxes `[ ]` /
 *  `[x]`. The order in the regex matters — longer patterns (markdown
 *  links) must match before bare URLs so `[txt](http://x)` doesn't
 *  swallow the URL into a separate token. */
function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  // Tokens in priority order.
  const re = /(\[[ xX]\] )|(`[^`\n]+`)|(\*\*[^*]+\*\*)|(~~[^~]+~~)|(\*[^*\n]+\*)|(\[[^\]]+\]\([^)]+\))|(https?:\/\/[^\s<>`)\]]+)/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) {
      const slice = text.slice(lastIdx, m.index);
      const withTt = withTooltips(slice);
      if (Array.isArray(withTt)) parts.push(...withTt);
      else parts.push(withTt);
    }
    const tok = m[0];
    if (/^\[[ xX]\] /.test(tok)) {
      const checked = /[xX]/.test(tok[1]);
      parts.push(
        <input
          key={`cb${key++}`}
          type="checkbox"
          disabled
          checked={checked}
          className="mr-1.5 align-middle accent-accent"
        />,
      );
    } else if (tok.startsWith('`')) {
      parts.push(
        <code
          key={`c${key++}`}
          className="px-1.5 py-0.5 rounded bg-bg-hover border border-border-subtle font-mono text-[12px] text-accent"
        >
          {tok.slice(1, -1)}
        </code>,
      );
    } else if (tok.startsWith('**')) {
      parts.push(
        <strong key={`b${key++}`} className="font-semibold text-fg">
          {tok.slice(2, -2)}
        </strong>,
      );
    } else if (tok.startsWith('~~')) {
      parts.push(
        <del key={`d${key++}`} className="text-fg-subtle">
          {tok.slice(2, -2)}
        </del>,
      );
    } else if (tok.startsWith('*')) {
      parts.push(
        <em key={`i${key++}`} className="italic">
          {tok.slice(1, -1)}
        </em>,
      );
    } else if (tok.startsWith('[')) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok);
      if (linkMatch) {
        parts.push(
          <a
            key={`a${key++}`}
            href={linkMatch[2]}
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:underline"
          >
            {linkMatch[1]}
          </a>,
        );
      } else {
        parts.push(tok);
      }
    } else if (tok.startsWith('http://') || tok.startsWith('https://')) {
      // Trim trailing punctuation that the user probably didn't mean
      // to include in the URL ("see http://x." → "see <a>http://x</a>.").
      const trimmed = tok.replace(/[.,;:!?)\]]+$/, '');
      const tail = tok.slice(trimmed.length);
      parts.push(
        <a
          key={`u${key++}`}
          href={trimmed}
          target="_blank"
          rel="noreferrer"
          className="text-accent hover:underline break-all"
        >
          {trimmed}
        </a>,
      );
      if (tail) parts.push(tail);
    }
    lastIdx = m.index + tok.length;
  }
  if (lastIdx < text.length) {
    const slice = text.slice(lastIdx);
    const withTt = withTooltips(slice);
    if (Array.isArray(withTt)) parts.push(...withTt);
    else parts.push(withTt);
  }
  return parts;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch { /* noop */ }
  };

  const highlighted = useMemo(() => {
    const normalised = (lang || '').toLowerCase().trim();
    try {
      if (normalised && hljs.getLanguage(normalised)) {
        return hljs.highlight(code, { language: normalised, ignoreIllegals: true }).value;
      }
      return hljs.highlightAuto(code, [
        'javascript', 'typescript', 'python', 'json', 'bash',
        'html', 'css', 'sql', 'yaml', 'markdown',
      ]).value;
    } catch {
      return code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }
  }, [lang, code]);

  return (
    <div className="my-2 rounded-md border border-border-subtle bg-bg-sidebar overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle bg-bg-titlebar">
        <span className="text-[11px] font-mono text-fg-subtle uppercase tracking-wider">
          {lang || 'text'}
        </span>
        <button
          onClick={onCopy}
          className={cn(
            'inline-flex items-center gap-1 h-6 px-2 rounded text-[11px]',
            'text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors',
          )}
          title="Copy code"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="px-3 py-2.5 overflow-x-auto text-[12.5px] leading-relaxed">
        <code
          className="hljs font-mono whitespace-pre"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </pre>
    </div>
  );
}

function TableBlock({
  head, aligns, rows,
}: { head: string[]; aligns: Align[]; rows: string[][] }) {
  const alignCls: Record<Align, string> = {
    left: 'text-left',
    center: 'text-center',
    right: 'text-right',
  };
  return (
    <div className="my-3 overflow-x-auto rounded-lg border border-border-subtle">
      <table className="w-full border-collapse text-xs">
        <thead className="bg-bg-hover">
          <tr>
            {head.map((h, i) => (
              <th
                key={i}
                className={cn(
                  'px-3 py-2 font-semibold text-fg whitespace-nowrap border-b border-border-subtle',
                  alignCls[aligns[i] ?? 'left'],
                )}
              >
                {renderInline(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="border-b border-border-subtle last:border-b-0">
              {r.map((cell, ci) => (
                <td
                  key={ci}
                  className={cn(
                    'px-3 py-1.5 text-fg-muted align-top',
                    alignCls[aligns[ci] ?? 'left'],
                  )}
                >
                  {renderInline(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MarkdownText({ source }: { source: string }) {
  const blocks = parseBlocks(source);
  return (
    <div className="text-sm text-fg leading-relaxed space-y-2">
      {blocks.map((b, idx) => {
        if (b.kind === 'code') return <CodeBlock key={idx} lang={b.lang} code={b.code} />;
        if (b.kind === 'hr') return <hr key={idx} className="border-border-subtle my-3" />;
        if (b.kind === 'table') return <TableBlock key={idx} head={b.head} aligns={b.aligns} rows={b.rows} />;
        if (b.kind === 'h') {
          const sizes: Record<number, string> = {
            2: 'text-base font-semibold mt-3',
            3: 'text-sm font-semibold mt-2 text-fg',
            4: 'text-sm font-medium mt-1.5 text-fg-muted',
          };
          return (
            <div key={idx} className={sizes[b.level]}>
              {renderInline(b.text)}
            </div>
          );
        }
        if (b.kind === 'ul') {
          return (
            <ul key={idx} className="list-disc list-outside pl-5 space-y-1">
              {b.items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}
            </ul>
          );
        }
        if (b.kind === 'ol') {
          return (
            <ol key={idx} className="list-decimal list-outside pl-5 space-y-1">
              {b.items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}
            </ol>
          );
        }
        return (
          <p key={idx} className="whitespace-pre-wrap">
            {renderInline(b.text)}
          </p>
        );
      })}
    </div>
  );
}
