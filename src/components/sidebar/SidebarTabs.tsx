import {
  MessageSquare,
  ListTree,
  Code2,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore, type SidebarTab } from '@/store/useAppStore';

interface TabDef {
  id: SidebarTab;
  icon: LucideIcon;
  label: string;
}

const TABS: TabDef[] = [
  { id: 'chat', icon: MessageSquare, label: 'Chat' },
  { id: 'tree', icon: ListTree, label: 'Tree' },
  { id: 'code', icon: Code2, label: 'Code' },
];

export default function SidebarTabs() {
  const active = useAppStore((s) => s.sidebarTab);
  const setTab = useAppStore((s) => s.setSidebarTab);

  return (
    <div className="px-2 py-2 flex items-center gap-1">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => setTab(tab.id)}
            title={tab.label}
            className={cn(
              'h-7 flex items-center gap-1.5 rounded-md transition-colors',
              isActive
                ? 'bg-bg-panel text-fg px-2.5'
                : 'text-fg-muted hover:bg-bg-hover hover:text-fg px-1.5',
            )}
          >
            <Icon size={14} strokeWidth={1.75} />
            {isActive && (
              <span className="text-xs font-medium">{tab.label}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
