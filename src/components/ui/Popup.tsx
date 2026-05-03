import { useEffect, useRef } from 'react';
import { cn } from '@/lib/cn';

interface Props {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  /** Position hint — the popup is absolutely placed by the parent via className. */
  className?: string;
}

/**
 * Minimal controlled popup. Parent is responsible for positioning via className
 * (the popup uses `absolute` and the parent supplies top/left/bottom anchors).
 * Click outside + Escape close it.
 */
export default function Popup({ open, onClose, children, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    // Defer so the click that opened it isn't caught immediately.
    const t = setTimeout(() => {
      document.addEventListener('mousedown', onDocClick);
      document.addEventListener('keydown', onKey);
    }, 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      ref={ref}
      className={cn(
        'absolute z-50 min-w-[200px] rounded-lg bg-bg-panel border border-border shadow-popup',
        'py-1.5',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PopupSection({ label }: { label: string }) {
  return (
    <div className="px-3 pt-2 pb-1 text-2xs font-medium text-fg-subtle uppercase tracking-wider">
      {label}
    </div>
  );
}

export function PopupItem({
  children,
  onClick,
  selected,
  trailing,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
  trailing?: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center justify-between px-3 py-1.5 text-sm',
        'text-fg hover:bg-bg-hover transition-colors',
      )}
    >
      <span>{children}</span>
      {selected ? (
        <span className="text-fg-muted">✓</span>
      ) : (
        trailing ?? null
      )}
    </button>
  );
}

export function PopupDivider() {
  return <div className="my-1 border-t border-border-subtle" />;
}
