import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/cn';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
  position?: 'top' | 'bottom';
}

export default function Tooltip({ content, children, className, contentClassName, position = 'top' }: TooltipProps) {
  const [show, setShow] = useState(false);
  const [coords, setCoords] = useState({ x: 0, y: 0, height: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (show && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setCoords({
        x: rect.left + rect.width / 2,
        y: rect.top,
        height: rect.height,
      });
    }
  }, [show]);

  useEffect(() => {
    if (!show) return;
    const handleScroll = () => setShow(false);
    window.addEventListener('scroll', handleScroll, true);
    return () => window.removeEventListener('scroll', handleScroll, true);
  }, [show]);

  return (
    <div 
      ref={triggerRef}
      className={cn("relative inline-block cursor-help", className)}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className="border-b border-dashed border-fg-muted/50">{children}</span>
      {show && createPortal(
        <div 
          className="fixed z-[9999] pointer-events-none transition-opacity duration-200"
          style={{ 
            left: coords.x, 
            top: position === 'bottom' ? coords.y + coords.height : coords.y, 
            transform: position === 'bottom' ? 'translate(-50%, 0)' : 'translate(-50%, -100%)',
            marginTop: position === 'bottom' ? '6px' : '-6px'
          }}
        >
          <div className={cn("relative w-max max-w-xs px-2.5 py-1.5 text-xs font-normal text-fg bg-bg-sidebar rounded shadow-lg border border-border-subtle whitespace-normal text-left", contentClassName)}>
            {position === 'bottom' && (
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 -mb-px border-[5px] border-transparent border-b-border-subtle">
                <div className="absolute -bottom-[6px] -left-[4px] border-[4px] border-transparent border-b-bg-sidebar" />
              </div>
            )}
            {content}
            {position === 'top' && (
              <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px border-[5px] border-transparent border-t-border-subtle">
                <div className="absolute -top-[6px] -left-[4px] border-[4px] border-transparent border-t-bg-sidebar" />
              </div>
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
