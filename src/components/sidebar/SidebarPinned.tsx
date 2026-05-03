import { Pin } from 'lucide-react';

export default function SidebarPinned() {
  return (
    <div className="px-2 pt-3 pb-2">
      <div className="px-2 pb-1.5 text-2xs font-medium text-fg-subtle">
        Pinned
      </div>
      <div className="flex items-center gap-2 px-2 py-1.5 text-sm text-fg-faint">
        <Pin size={12} strokeWidth={1.75} />
        <span>Drag to pin</span>
      </div>
    </div>
  );
}
