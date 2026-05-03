import { useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';
import UserMenuPopup from './UserMenuPopup';

interface Props {
  displayName?: string;
}

export default function SidebarUserRow({ displayName = 'nitin soloman' }: Props) {
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const [menuOpen, setMenuOpen] = useState(false);

  const initial = (displayName[0] ?? 'U').toUpperCase();

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className="relative">
      <div
        onClick={() => setMenuOpen((v) => !v)}
        className={cn(
          'flex items-center gap-2 px-3 py-2.5 cursor-pointer',
          'hover:bg-bg-hover transition-colors',
        )}
      >
        <div
          className={cn(
            'w-6 h-6 rounded-full bg-bg-panel border border-border',
            'flex items-center justify-center text-[10px] font-medium text-fg-muted shrink-0',
          )}
        >
          {initial}
        </div>
        <span className="flex-1 text-sm truncate">{displayName}</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleTheme();
          }}
          className="p-1 rounded text-fg-muted hover:text-fg hover:bg-bg-hover"
          title="Toggle theme"
        >
          {theme === 'dark' ? <Moon size={13} /> : <Sun size={13} />}
        </button>
      </div>

      {menuOpen && (
        <UserMenuPopup
          onClose={() => setMenuOpen(false)}
        />
      )}
    </div>
  );
}
