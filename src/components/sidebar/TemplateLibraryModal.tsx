import React from 'react';
import { X, PlayCircle, BookOpen } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore, useActiveSession } from '@/store/useAppStore';

const TEMPLATES = [
  { 
    name: "VWAP Breakout", 
    desc: "Intraday mean-reversion using VWAP and RSI.", 
    prompt: "Build an intraday VWAP breakout strategy. Go long when price crosses above VWAP and RSI < 40. Keep stop loss tight." 
  },
  { 
    name: "Dual SuperTrend", 
    desc: "Trend following using fast and slow SuperTrends.", 
    prompt: "Design a Dual SuperTrend strategy on 5m timeframe. Fast=10/3, Slow=20/5. Only trade in the direction of a 200 EMA." 
  },
  { 
    name: "Bollinger Squeeze", 
    desc: "Volatility expansion breakout.", 
    prompt: "Build a Bollinger Bands squeeze breakout strategy. Enter when bandwidth expands rapidly after a long period of contraction." 
  },
  { 
    name: "MACD Crossover", 
    desc: "Classic trend momentum.", 
    prompt: "Build a classic MACD crossover strategy with a 200 EMA trend filter. Add a time-based exit to prevent holding too long." 
  }
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function TemplateLibraryModal({ open, onClose }: Props) {
  const session = useActiveSession();
  const setChatDraft = useAppStore((s) => s.setChatDraft);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-[500px] bg-bg-panel border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-bg-titlebar">
          <div className="flex items-center gap-2 text-fg">
            <BookOpen size={18} className="text-accent" />
            <h2 className="font-semibold">Strategy Templates</h2>
          </div>
          <button onClick={onClose} className="text-fg-muted hover:text-fg transition-colors">
            <X size={18} />
          </button>
        </div>
        
        <div className="p-4 space-y-3 max-h-[60vh] overflow-y-auto">
          <p className="text-sm text-fg-subtle mb-4">
            Select a pre-built template to quickly kickstart your strategy research.
          </p>
          
          {TEMPLATES.map((t, i) => (
            <div 
              key={i}
              className="flex items-start justify-between p-3 rounded-lg border border-border-subtle bg-bg-sidebar hover:border-accent/50 transition-colors group"
            >
              <div>
                <h3 className="text-sm font-medium text-fg">{t.name}</h3>
                <p className="text-xs text-fg-muted mt-1">{t.desc}</p>
              </div>
              <button
                onClick={() => {
                  setChatDraft(t.prompt);
                  onClose();
                  // Note: The user can just hit enter in the chat input. 
                  // If no session is active, it just pre-fills the draft globally.
                }}
                className="shrink-0 ml-4 flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent/10 text-accent opacity-0 group-hover:opacity-100 transition-opacity hover:bg-accent hover:text-white text-xs font-medium"
              >
                <PlayCircle size={14} />
                Use
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
