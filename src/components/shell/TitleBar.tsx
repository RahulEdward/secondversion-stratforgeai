import {
  PanelLeft,
  Search,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import RightPaneMenu from './RightPaneMenu';

interface Props {
  onToggleSidebar?: () => void;
  sidebarOpen?: boolean;
}

function IconBtn({
  title,
  children,
  onClick,
  disabled,
}: {
  title: string;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'no-drag h-7 w-7 flex items-center justify-center rounded',
        'text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent',
      )}
    >
      {children}
    </button>
  );
}

export default function TitleBar({ onToggleSidebar, sidebarOpen }: Props) {
  return (
    <div
      className={cn(
        'drag-region h-10 shrink-0 bg-bg-sidebar',
        // pr reserves space for the native Windows min/max/close overlay on the right.
        'flex items-center pl-2 pr-36 gap-0.5 select-none',
      )}
    >
      <IconBtn
        title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
        onClick={onToggleSidebar}
      >
        <PanelLeft size={15} strokeWidth={1.75} />
      </IconBtn>
      <IconBtn title="Search">
        <Search size={15} strokeWidth={1.75} />
      </IconBtn>
      <div className="w-2" />
      <IconBtn title="Back" disabled>
        <ChevronLeft size={16} strokeWidth={1.75} />
      </IconBtn>
      <IconBtn title="Forward" disabled>
        <ChevronRight size={16} strokeWidth={1.75} />
      </IconBtn>
      {/* drag region fills the remaining space; window controls are native */}
      <div className="flex-1 h-full" />

      {/* App Name & Version (Absolute Centered) */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2 text-xs font-semibold text-fg-muted select-none pointer-events-none">
        <span>StratForge AI</span>
        <span className="text-[10px] font-medium bg-bg-hover px-1.5 py-0.5 rounded-md border border-border">
          v0.1.0
        </span>
      </div>
      {/* Claude Code-style right-pane mode menu (Preview / Diff / Terminal /
          Files / Tasks / Plan). Sits before the native window controls. */}
      {/* Claude Code-style right-pane mode menu (Preview / Diff / Terminal /
          Files / Tasks / Plan). Sits before the native window controls. */}
      <div className="flex items-center gap-1">
        <RightPaneMenu />
      </div>
    </div>
  );
}
