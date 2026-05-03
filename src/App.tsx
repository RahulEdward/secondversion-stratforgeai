import { useEffect, useState } from 'react';
import TitleBar from './components/shell/TitleBar';
import Sidebar from './components/Sidebar';
import SidebarCollapsed from './components/SidebarCollapsed';
import ChatPane from './components/ChatPane';
import ArtifactsPane from './components/ArtifactsPane';
import SettingsPage from './components/settings/SettingsPage';
import { ToastHost } from './components/ui/Toast';
import { useAppStore } from './store/useAppStore';

export default function App() {
  const init = useAppStore((s) => s.init);
  const artifactsOpen = useAppStore((s) => s.artifactsOpen);
  const settingsOpen = useAppStore((s) => s.settingsOpen);
  const theme = useAppStore((s) => s.theme);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    init();
  }, [init]);

  useEffect(() => {
    const root = document.documentElement;
    const resolved =
      theme === 'system'
        ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
        : theme;
    root.classList.remove('light', 'dark');
    root.classList.add(resolved);
    const bridge = (window as unknown as { stratforge?: { setTitleBarTheme?: (t: 'light' | 'dark') => Promise<void> } }).stratforge;
    bridge?.setTitleBarTheme?.(resolved);
  }, [theme]);

  return (
    <div className="flex flex-col h-screen bg-bg text-fg font-sans text-sm">
      <TitleBar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
      />
      <div className="flex flex-1 min-h-0">
        {sidebarOpen ? <Sidebar /> : <SidebarCollapsed />}
        <ChatPane />
        {artifactsOpen && <ArtifactsPane />}
      </div>
      <ToastHost />
      {settingsOpen && <SettingsPage />}
    </div>
  );
}
