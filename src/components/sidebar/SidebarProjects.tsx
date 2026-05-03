import { useState } from 'react';
import { Circle, MoreHorizontal, Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';
import type { Project, Session } from '@/lib/api';
import NewProjectDialog from '../NewProjectDialog';
import SidebarDatasets from './SidebarDatasets';

function SessionRow({
  session,
  active,
  onSelect,
  onDelete,
}: {
  session: Session;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        'group w-full flex items-center gap-2 pl-3 pr-2 py-1.5 rounded cursor-pointer text-sm transition-colors',
        active
          ? 'bg-bg-active text-fg'
          : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
      )}
    >
      {active ? (
        <MoreHorizontal size={13} className="shrink-0" strokeWidth={1.75} />
      ) : (
        <Circle size={9} className="shrink-0" strokeWidth={1.75} />
      )}
      <span className="truncate flex-1">{session.title}</span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-bg-hover hover:text-red-400 transition-opacity"
        title="Delete session"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

function ProjectGroup({ project }: { project: Project }) {
  const sessions = useAppStore((s) => s.sessionsByProject[project.id] ?? []);
  const activeSessionId = useAppStore((s) => s.activeSessionId);
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const setActiveSession = useAppStore((s) => s.setActiveSession);
  const setActiveProject = useAppStore((s) => s.setActiveProject);
  const createSession = useAppStore((s) => s.createSession);
  const deleteSession = useAppStore((s) => s.deleteSession);
  const deleteProject = useAppStore((s) => s.deleteProject);

  const [hover, setHover] = useState(false);
  const isActiveProject = activeProjectId === project.id;

  const handleNewSession = async () => {
    await createSession(project.id, 'New session');
  };

  const handleDeleteProject = async () => {
    if (
      !confirm(
        `Delete project "${project.name}"? All sessions + data removed.`,
      )
    )
      return;
    await deleteProject(project.id);
  };

  const handleDeleteSession = async (sid: string) => {
    if (!confirm('Delete this session?')) return;
    await deleteSession(sid);
  };

  return (
    <div
      className="mb-1"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        onClick={() => setActiveProject(project.id)}
        className={cn(
          'group flex items-center justify-between px-2 py-1 cursor-pointer',
          'text-xs font-normal transition-colors',
          isActiveProject ? 'text-fg' : 'text-fg-subtle hover:text-fg-muted',
        )}
      >
        <span className="truncate">{project.name}</span>
        <div
          className={cn(
            'flex items-center gap-0.5 transition-opacity',
            hover ? 'opacity-100' : 'opacity-0',
          )}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleNewSession();
            }}
            className="p-0.5 rounded hover:bg-bg-hover hover:text-fg"
            title="New session in this project"
          >
            <Plus size={11} />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDeleteProject();
            }}
            className="p-0.5 rounded hover:bg-bg-hover hover:text-red-400"
            title="Delete project"
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>
      {isActiveProject && <SidebarDatasets projectId={project.id} />}
      <div className="space-y-0.5">
        {sessions.length === 0 ? (
          <div className="pl-3 pr-2 py-1 text-xs text-fg-faint italic">
            No sessions — click + to create
          </div>
        ) : (
          sessions.map((s) => (
            <SessionRow
              key={s.id}
              session={s}
              active={activeSessionId === s.id}
              onSelect={() => setActiveSession(s.id)}
              onDelete={() => handleDeleteSession(s.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default function SidebarProjects() {
  const projects = useAppStore((s) => s.projects);
  const ready = useAppStore((s) => s.ready);
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <div className="flex-1 overflow-y-auto px-2 py-2 min-h-0">
        <div className="flex items-center justify-between px-2 pb-1">
          <span className="text-2xs font-medium text-fg-subtle uppercase tracking-wider">
            Projects
          </span>
          <button
            onClick={() => setDialogOpen(true)}
            className="p-0.5 rounded text-fg-subtle hover:bg-bg-hover hover:text-fg"
            title="New project"
          >
            <Plus size={12} />
          </button>
        </div>
        {!ready ? (
          <div className="px-2 py-1 text-xs text-fg-subtle italic">Loading…</div>
        ) : projects.length === 0 ? (
          <div className="px-2 py-2 text-xs text-fg-subtle italic leading-relaxed">
            No projects yet. Click + to create one.
          </div>
        ) : (
          projects.map((p) => <ProjectGroup key={p.id} project={p} />)
        )}
      </div>
      <NewProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
      />
    </>
  );
}
