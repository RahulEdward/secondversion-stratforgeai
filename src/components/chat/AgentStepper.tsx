import React, { useMemo } from 'react';
import { Database, BrainCircuit, CheckCircle2, FlaskConical, Target } from 'lucide-react';
import { cn } from '@/lib/cn';

interface Props {
  text: string;
}

const STEPS = [
  { id: 1, label: 'Data Analyst', icon: Database, keyword: 'Phase 1' },
  { id: 2, label: 'Architect', icon: BrainCircuit, keyword: 'Phase 2' },
  { id: 3, label: 'Backtester', icon: FlaskConical, keyword: 'Phase 3' },
  { id: 4, label: 'Evaluator', icon: Target, keyword: 'Phase 4' },
];

export default function AgentStepper({ text }: Props) {
  if (!text.includes('Phase 1 — Data Reconnaissance')) {
    return null;
  }

  const currentStep = useMemo(() => {
    let step = 1;
    if (text.includes('Phase 2')) step = 2;
    if (text.includes('Phase 3')) step = 3;
    if (text.includes('Phase 4')) step = 4;
    if (text.includes('✅ **Final Status')) step = 5;
    if (text.includes('✅ **Finished**')) step = 5;
    return step;
  }, [text]);

  return (
    <div className="flex items-center w-full justify-between mb-4 mt-2 border border-border-subtle rounded-xl bg-bg-sidebar px-4 py-3 relative overflow-hidden">
      <div className="absolute top-0 left-0 h-[2px] bg-border-strong w-full" />
      <div 
        className="absolute top-0 left-0 h-[2px] bg-accent transition-all duration-500 ease-out" 
        style={{ width: `${Math.min(100, ((currentStep - 1) / 3) * 100)}%` }}
      />
      
      {STEPS.map((step) => {
        const Icon = step.icon;
        const isActive = currentStep === step.id;
        const isPast = currentStep > step.id;
        const isDone = currentStep === 5;
        
        return (
          <div key={step.id} className="flex flex-col items-center gap-1.5 z-10 flex-1 relative">
            <div 
              className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center transition-colors duration-300 border-2 bg-bg-panel",
                isActive ? "border-accent text-accent shadow-[0_0_12px_rgba(200,90,50,0.3)] animate-pulse" : 
                isPast || isDone ? "border-emerald-500 text-emerald-500" : 
                "border-border-strong text-fg-subtle"
              )}
            >
              {isPast || isDone ? <CheckCircle2 size={16} /> : <Icon size={16} />}
            </div>
            <span 
              className={cn(
                "text-[10px] font-bold tracking-wider uppercase text-center whitespace-nowrap",
                isActive ? "text-accent" :
                isPast || isDone ? "text-emerald-500" :
                "text-fg-subtle"
              )}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
