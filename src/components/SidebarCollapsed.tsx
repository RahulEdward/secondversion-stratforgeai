import { Plus, Search, MoreHorizontal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';
import { toast } from './ui/Toast';

interface Props {
  onNewSession?: () => void;
}

interface RailItemProps {
  icon: LucideIcon;
  title: string;
  onClick?: () => void;
}

function RailItem({ icon: Icon, title, onClick }: RailItemProps) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={cn(
        'h-8 w-8 flex items-center justify-center rounded',
        'text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors',
      )}
    >
      <Icon size={15} strokeWidth={1.75} />
    </button>
  );
}

/**
 * Narrow icon rail shown in place of the full Sidebar when the user toggles
 * it closed. Mirrors the primary sidebar actions as icon-only buttons plus
 * the user avatar at the bottom so the rail never feels empty.
 */
export default function SidebarCollapsed({ onNewSession }: Props) {
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const openSettings = useAppStore((s) => s.openSettings);

  const handleNewSession = () => {
    if (onNewSession) return onNewSession();
    if (!activeProjectId) toast('Select or create a project first');
  };

  return (
    <aside
      className={cn(
        'w-[52px] bg-bg-sidebar border-r border-border',
        'flex flex-col items-center shrink-0 min-h-0 py-2 gap-1',
      )}
    >
      <RailItem icon={Plus} title="New session" onClick={handleNewSession} />
      <RailItem
        icon={Search}
        title="Search"
        onClick={() => toast('Search — coming soon')}
      />
      <RailItem
        icon={MoreHorizontal}
        title="More"
        onClick={() => openSettings('general')}
      />

      {/* Spacer pushes the avatar to the bottom. */}
      <div className="flex-1" />

      <button
        title="Account"
        onClick={() => openSettings('general')}
        className={cn(
          'w-7 h-7 rounded-full bg-bg-panel border border-border',
          'flex items-center justify-center text-[10px] font-medium text-fg-muted',
          'hover:text-fg hover:bg-bg-hover transition-colors',
        )}
      >
        N
      </button>
    </aside>
  );
}
