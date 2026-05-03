import { useCallback, useEffect, useRef } from 'react';
import { cn } from '@/lib/cn';

interface Props {
  /** Which edge of the sibling element this handle resizes. ``right``
   *  drags-right to grow, ``left`` drags-left to grow. */
  side: 'right' | 'left';
  /** Initial width in px. */
  width: number;
  /** Called with the new width on every drag tick. */
  onResize: (next: number) => void;
  min?: number;
  max?: number;
}

/** A 4px-wide drag handle absolute-positioned on one edge of its parent.
 *  Parent should be ``relative``. Drag updates ``onResize`` continuously.
 */
export default function ResizeHandle({
  side, width, onResize, min = 220, max = 800,
}: Props) {
  const startX = useRef(0);
  const startW = useRef(width);
  const isDragging = useRef(false);

  const onMove = useCallback((e: MouseEvent) => {
    if (!isDragging.current) return;
    const dx = e.clientX - startX.current;
    const next = side === 'right' ? startW.current + dx : startW.current - dx;
    onResize(Math.max(min, Math.min(max, next)));
  }, [side, onResize, min, max]);

  const onUp = useCallback(() => {
    if (!isDragging.current) return;
    isDragging.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  }, [onMove]);

  const onDown = (e: React.MouseEvent) => {
    e.preventDefault();
    startX.current = e.clientX;
    startW.current = width;
    isDragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  useEffect(() => () => {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  }, [onMove, onUp]);

  return (
    <div
      onMouseDown={onDown}
      onDoubleClick={() => onResize(side === 'right' ? 280 : 440)}
      className={cn(
        'absolute top-0 bottom-0 w-1 z-30 cursor-col-resize group',
        'hover:bg-accent/30 active:bg-accent/50 transition-colors',
        side === 'right' ? '-right-0.5' : '-left-0.5',
      )}
      title="Drag to resize · double-click to reset"
    >
      {/* Wider invisible hit area so the user doesn't have to land on the
          1-pixel divider exactly. */}
      <div className={cn(
        'absolute top-0 bottom-0 w-3',
        side === 'right' ? '-right-1' : '-left-1',
      )} />
    </div>
  );
}
