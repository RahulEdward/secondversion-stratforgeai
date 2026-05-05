import { useState } from 'react';
import { Folder, ChevronDown, PanelRight, Database, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import {
  useAppStore,
  useActiveProject,
  useActiveSession,
  useActiveDataset,
} from '@/store/useAppStore';
import Popup, { PopupItem, PopupSection } from '../ui/Popup';
import RightPaneMenu from '../shell/RightPaneMenu';

export default function MainHeader() {
  const project = useActiveProject();
  const session = useActiveSession();
  const dataset = useActiveDataset();
  const sessionsByProject = useAppStore((s) => s.sessionsByProject);
  const datasetsByProject = useAppStore((s) => s.datasetsByProject);
  const setActiveSession = useAppStore((s) => s.setActiveSession);
  const setActiveDataset = useAppStore((s) => s.setActiveDataset);
  const createSession = useAppStore((s) => s.createSession);

  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [datasetPickerOpen, setDatasetPickerOpen] = useState(false);

  const projectSessions = project ? sessionsByProject[project.id] ?? [] : [];
  const projectDatasets = project ? datasetsByProject[project.id] ?? [] : [];

  const breadcrumb = (() => {
    if (!project) return 'No project selected';
    if (!session) return project.name;
    return (
      <>
        <span className="text-fg-muted">{project.name}</span>
        <span className="px-2 text-fg-subtle">/</span>
        <span className="text-fg">{session.title}</span>
      </>
    );
  })();

  return (
    <header className="h-11 shrink-0 flex items-center justify-between px-4">
      <div className="flex items-center min-w-0 gap-2">
        <div className="relative flex items-center min-w-0">
          <Folder size={14} className="text-fg-muted mr-2 shrink-0" />
          <button
            onClick={() => project && setSwitcherOpen((v) => !v)}
            className={cn(
              'flex items-center gap-1.5 text-sm min-w-0 rounded px-1.5 py-0.5',
              'hover:bg-bg-hover transition-colors',
            )}
            disabled={!project}
          >
            <span className="truncate">{breadcrumb}</span>
            {project && (
              <ChevronDown size={12} className="text-fg-muted shrink-0" />
            )}
          </button>
          {switcherOpen && project && (
            <Popup
              open
              onClose={() => setSwitcherOpen(false)}
              className="top-9 left-4 min-w-[280px]"
            >
              <PopupSection label="Sessions in this project" />
              {projectSessions.length === 0 ? (
                <div className="px-3 py-2 text-xs text-fg-subtle italic">
                  No sessions yet
                </div>
              ) : (
                projectSessions.map((s) => (
                  <PopupItem
                    key={s.id}
                    selected={session?.id === s.id}
                    onClick={() => {
                      void setActiveSession(s.id);
                      setSwitcherOpen(false);
                    }}
                  >
                    {s.title}
                  </PopupItem>
                ))
              )}
              <div className="my-1 border-t border-border-subtle" />
              <PopupItem
                onClick={() => {
                  void createSession(project.id, 'New session');
                  setSwitcherOpen(false);
                }}
              >
                + New session
              </PopupItem>
            </Popup>
          )}
        </div>

        {project && projectDatasets.length > 0 && (
          <div className="relative flex items-center">
            <span className="text-fg-subtle px-1">·</span>
            <button
              onClick={() => setDatasetPickerOpen((v) => !v)}
              className={cn(
                'flex items-center gap-1.5 text-xs rounded pl-1.5 pr-1 py-0.5',
                'hover:bg-bg-hover transition-colors',
                dataset ? 'text-fg' : 'text-fg-muted',
              )}
              title={dataset ? 'Active dataset' : 'Pick a dataset'}
            >
              <Database
                size={11}
                strokeWidth={1.75}
                className={dataset ? 'text-accent' : 'text-fg-subtle'}
              />
              <span className="truncate max-w-[180px]">
                {dataset ? dataset.filename : 'No dataset'}
              </span>
              <ChevronDown size={10} className="text-fg-muted" />
            </button>
            {dataset && (
              <button
                onClick={() => setActiveDataset(null)}
                className="ml-0.5 p-0.5 rounded text-fg-muted hover:bg-bg-hover hover:text-fg"
                title="Clear active dataset"
              >
                <X size={10} />
              </button>
            )}
            {datasetPickerOpen && (
              <Popup
                open
                onClose={() => setDatasetPickerOpen(false)}
                className="top-8 left-4 min-w-[260px]"
              >
                <PopupSection label="Datasets in this project" />
                {projectDatasets.map((d) => (
                  <PopupItem
                    key={d.id}
                    selected={dataset?.id === d.id}
                    onClick={() => {
                      setActiveDataset(d.id);
                      setDatasetPickerOpen(false);
                    }}
                    trailing={
                      <span className="text-2xs text-fg-subtle tabular-nums">
                        {d.rows}
                      </span>
                    }
                  >
                    {d.filename}
                  </PopupItem>
                ))}
              </Popup>
            )}
          </div>
        )}
      </div>

      <RightPaneMenu />
    </header>
  );
}
