import type { LucideIcon } from 'lucide-react';
import {
  Settings as GeneralIcon,
  Plug,
  Zap,
  Puzzle,
  Cloud,
  CreditCard,
  BarChart3,
  BookOpen,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore, type SettingsSection } from '@/store/useAppStore';

interface NavItem {
  id: SettingsSection;
  label: string;
  icon: LucideIcon;
  enabled: boolean;
}

const ITEMS: NavItem[] = [
  { id: 'general', label: 'General', icon: GeneralIcon, enabled: true },
  { id: 'providers', label: 'Providers', icon: Plug, enabled: true },
  { id: 'automations', label: 'Automations', icon: Zap, enabled: false },
  { id: 'plugins', label: 'Plugins', icon: Puzzle, enabled: false },
  { id: 'remote', label: 'Remote', icon: Cloud, enabled: false },
  { id: 'billing', label: 'Billing', icon: CreditCard, enabled: false },
  { id: 'usage', label: 'Usage', icon: BarChart3, enabled: false },
  { id: 'memory', label: 'Memory', icon: BookOpen, enabled: true },
];

export default function SettingsNav() {
  const section = useAppStore((s) => s.settingsSection);
  const setSection = useAppStore((s) => s.setSettingsSection);

  return (
    <nav className="flex flex-col gap-0.5 p-3 w-56 border-r border-border bg-bg-sidebar shrink-0">
      <div className="px-2 pb-3 text-xs font-medium text-fg-subtle uppercase tracking-wider">
        Settings
      </div>
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const active = section === item.id;
        return (
          <button
            key={item.id}
            disabled={!item.enabled}
            onClick={() => item.enabled && setSection(item.id)}
            className={cn(
              'flex items-center gap-2.5 px-2.5 py-1.5 rounded text-sm text-left',
              'transition-colors',
              active
                ? 'bg-bg-active text-fg'
                : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
              !item.enabled && 'opacity-40 cursor-not-allowed hover:bg-transparent hover:text-fg-muted',
            )}
            title={item.enabled ? undefined : 'Coming soon'}
          >
            <Icon size={14} strokeWidth={1.75} />
            <span className="flex-1">{item.label}</span>
            {!item.enabled && (
              <span className="text-[10px] text-fg-faint">soon</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
