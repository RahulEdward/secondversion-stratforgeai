import React, { useMemo } from 'react';
import { Brain, Database, Map, BrainCircuit, FlaskConical, Target, Search, Flag, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/cn';

interface Props {
  text: string;
}

const STEPS = [
  { id: 1, label: 'Intent', icon: Brain, keyword: 'Step 1' },
  { id: 2, label: 'Analyst', icon: Database, keyword: 'Step 2' },
  { id: 3, label: 'Planner', icon: Map, keyword: 'Step 3' },
  { id: 4, label: 'Architect', icon: BrainCircuit, keyword: 'Step 4' },
  { id: 5, label: 'Backtest', icon: FlaskConical, keyword: 'Step 5' },
  { id: 6, label: 'Evaluate', icon: Target, keyword: 'Step 6' },
  { id: 7, label: 'Critic', icon: Search, keyword: 'Step 7' },
  { id: 8, label: 'Finalize', icon: Flag, keyword: 'Step 8' },
];

export default function AgentStepper({ text }: Props) {
  // Only show if the research pipeline has started
  if (!text.includes('Step 1') && !text.includes('Phase 1 — Data Reconnaissance')) {
    return null;
  }

  const currentStep = useMemo(() => {
    let step = 1;
    if (text.includes('Step 2') || text.includes('Phase 1 — Data')) step = 2;
    if (text.includes('Step 3') || text.includes('Phase 2')) step = 3;
    if (text.includes('Step 4') || text.includes('Designing Strategies') || text.includes('Phase 2')) step = 4;
    if (text.includes('Step 5') || text.includes('Testing') || text.includes('Phase 3')) step = 5;
    if (text.includes('Step 6') || text.includes('Evaluating') || text.includes('Phase 4')) step = 6;
    if (text.includes('Step 7') || text.includes('Critic')) step = 7;
    if (text.includes('Step 8') || text.includes('Finalizing')) step = 8;
    if (text.includes('Research Complete') || text.includes('✅ **Final Status') || text.includes('✅ **Finished**')) step = 9;
    return step;
  }, [text]);

  // Extract live stats from the text
  const stats = useMemo(() => {
    const s: { variants?: string; grade?: string; iteration?: string } = {};
    const variantMatch = text.match(/Total:\s*(\d+)\s*variants/);
    if (variantMatch) s.variants = variantMatch[1];
    const gradeMatch = text.match(/Grade=\*\*([A-F][+-]?)\*\*/);
    if (gradeMatch) s.grade = gradeMatch[1];
    const iterMatch = text.match(/Iteration\s*(\d+)\/(\d+)/);
    if (iterMatch) s.iteration = `${iterMatch[1]}/${iterMatch[2]}`;
    return s;
  }, [text]);

  const totalSteps = STEPS.length;
  const progressPct = Math.min(100, ((currentStep - 1) / totalSteps) * 100);

  return (
    <div className="mb-4 mt-2 border border-border-subtle rounded-xl bg-bg-sidebar overflow-hidden">
      {/* Progress bar */}
      <div className="relative h-[3px] bg-border-strong">
        <div
          className="absolute top-0 left-0 h-full bg-gradient-to-r from-accent via-amber-500 to-emerald-500 transition-all duration-700 ease-out"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Steps */}
      <div className="flex items-center justify-between px-3 py-2.5">
        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isActive = currentStep === step.id;
          const isPast = currentStep > step.id;
          const isDone = currentStep === 9;

          return (
            <React.Fragment key={step.id}>
              <div className="flex flex-col items-center gap-1 flex-1 relative">
                <div
                  className={cn(
                    "w-7 h-7 rounded-full flex items-center justify-center transition-all duration-300 border-[1.5px]",
                    isActive
                      ? "border-accent text-accent bg-accent/10 shadow-[0_0_10px_rgba(200,90,50,0.25)] scale-110"
                      : isPast || isDone
                      ? "border-emerald-500 text-emerald-500 bg-emerald-500/10"
                      : "border-border-strong text-fg-subtle bg-bg-panel"
                  )}
                >
                  {isPast || isDone ? (
                    <CheckCircle2 size={14} strokeWidth={2} />
                  ) : (
                    <Icon size={13} strokeWidth={isActive ? 2 : 1.5} className={isActive ? 'animate-pulse' : ''} />
                  )}
                </div>
                <span
                  className={cn(
                    "text-[9px] font-semibold tracking-wider uppercase text-center whitespace-nowrap leading-none",
                    isActive
                      ? "text-accent"
                      : isPast || isDone
                      ? "text-emerald-500"
                      : "text-fg-subtle"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {/* Connector line between steps */}
              {idx < STEPS.length - 1 && (
                <div
                  className={cn(
                    "h-[1.5px] flex-1 mx-0.5 mt-[-12px] transition-colors duration-300",
                    currentStep > step.id + 1 || isDone
                      ? "bg-emerald-500/60"
                      : currentStep === step.id + 1
                      ? "bg-accent/40"
                      : "bg-border-strong/50"
                  )}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Live stats bar */}
      {(stats.variants || stats.grade || stats.iteration) && (
        <div className="flex items-center gap-4 px-4 py-1.5 border-t border-border-subtle/50 bg-bg-panel/50">
          {stats.iteration && (
            <span className="text-[10px] text-fg-muted">
              🔄 Iter <span className="text-fg font-medium">{stats.iteration}</span>
            </span>
          )}
          {stats.variants && (
            <span className="text-[10px] text-fg-muted">
              📊 <span className="text-fg font-medium">{stats.variants}</span> variants
            </span>
          )}
          {stats.grade && (
            <span className="text-[10px] text-fg-muted">
              🏆 Best: <span className={cn(
                "font-bold",
                stats.grade.startsWith('A') ? "text-emerald-400" :
                stats.grade.startsWith('B') ? "text-amber-400" :
                "text-red-400"
              )}>{stats.grade}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
