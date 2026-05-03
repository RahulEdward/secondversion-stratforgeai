import React, { useState } from 'react';
import { cn } from '@/lib/cn';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export default function Tooltip({ content, children, className }: TooltipProps) {
  const [show, setShow] = useState(false);

  return (
    <div 
      className={cn("relative inline-block cursor-help", className)}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className="border-b border-dashed border-fg-muted/50">{children}</span>
      {show && (
        <div className="absolute z-[100] bottom-full left-1/2 -translate-x-1/2 mb-2 w-max max-w-xs px-2.5 py-1.5 text-xs font-normal text-fg bg-bg-sidebar rounded shadow-lg border border-border-subtle whitespace-normal text-left pointer-events-none transition-opacity duration-200">
          {content}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px border-[5px] border-transparent border-t-border-subtle">
            <div className="absolute -top-[6px] -left-[4px] border-[4px] border-transparent border-t-bg-sidebar" />
          </div>
        </div>
      )}
    </div>
  );
}
