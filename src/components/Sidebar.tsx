import SidebarNav from './sidebar/SidebarNav';
import SidebarProjects from './sidebar/SidebarProjects';
import SidebarUserRow from './sidebar/SidebarUserRow';
import { useAppStore } from '@/store/useAppStore';
import { toast } from './ui/Toast';
import ResizeHandle from './ResizeHandle';

export default function Sidebar() {
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const createSession = useAppStore((s) => s.createSession);
  const width = useAppStore((s) => s.sidebarWidth);
  const setWidth = useAppStore((s) => s.setSidebarWidth);

  const handleNewSession = () => {
    if (!activeProjectId) {
      toast('Select or create a project first');
      return;
    }
    void createSession(activeProjectId, 'New session');
  };

  return (
    <aside
      style={{ width: `${width}px` }}
      className="relative bg-bg-sidebar border-r border-border flex flex-col shrink-0 min-h-0"
    >
      <div className="pt-2" />
      <SidebarNav onNewSession={handleNewSession} />
      <SidebarProjects />
      <SidebarUserRow />
      <ResizeHandle side="right" width={width} onResize={setWidth} min={220} max={600} />
    </aside>
  );
}
