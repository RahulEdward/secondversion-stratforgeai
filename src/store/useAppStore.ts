import { create } from 'zustand';
import {
  Dataset,
  Project,
  ProviderInfo,
  Session,
  listProjects,
  createProject as apiCreateProject,
  renameProject as apiRenameProject,
  deleteProject as apiDeleteProject,
  listSessions,
  createSession as apiCreateSession,
  renameSession as apiRenameSession,
  deleteSession as apiDeleteSession,
  listDatasets,
  uploadDataset as apiUploadDataset,
  deleteDataset as apiDeleteDataset,
  getAppState,
  setAppState,
  listProviders,
  saveProviderKey as apiSaveProviderKey,
  deleteProviderKey as apiDeleteProviderKey,
  updateOllamaBaseUrl as apiUpdateOllamaBaseUrl,
  updateSessionModel as apiUpdateSessionModel,
  startChatGPTAuth as apiStartChatGPTAuth,
  pollChatGPTAuth as apiPollChatGPTAuth,
  signOutChatGPT as apiSignOutChatGPT,
  Message,
  listSessionMessages,
  openSessionStream,
} from '@/lib/api';
import {
  classifyArtifactIntent,
  findLatestReportInMessages,
} from '@/lib/artifactCommands';

export type Theme = 'light' | 'dark' | 'system';
export type SidebarTab = 'chat' | 'tree' | 'code';
export type PermissionMode = 'ask' | 'accept-edits' | 'plan' | 'bypass';

/** Claude Code-style right-pane modes. `null` keeps the current default
 *  (report iframe when an `activeReportId` exists, empty state otherwise). */
export type RightPaneMode =
  | 'preview'
  | 'diff'
  | 'terminal'
  | 'files'
  | 'tasks'
  | 'runtime'
  | null;

export interface TaskItem {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'done';
  notes?: string;
  created_at: string;
}
export type SettingsSection =
  | 'general'
  | 'providers'
  | 'automations'
  | 'plugins'
  | 'remote'
  | 'billing'
  | 'usage'
  | 'memory';

interface AppStore {
  // Server-owned
  projects: Project[];
  sessionsByProject: Record<string, Session[]>;
  datasetsByProject: Record<string, Dataset[]>;
  activeProjectId: string | null;
  activeSessionId: string | null;
  activeDatasetId: string | null;
  ready: boolean;
  error: string | null;

  // UI-only (not persisted server-side yet)
  sidebarTab: SidebarTab;
  artifactsOpen: boolean;
  /** Report id currently shown in the right artifacts pane. Auto-set when
   *  the chat stream surfaces a successful `render_report` tool_result. */
  activeReportId: string | null;
  /** Optional title surfaced from the render_report payload for the pane header. */
  activeReportTitle: string | null;
  /** Claude Code-style right-pane mode (Preview / Diff / Terminal / Files /
   *  Tasks / Plan). When null, the pane shows the active report or empty. */
  rightPaneMode: RightPaneMode;
  /** User-resizable widths (px) for the two side panes. Persisted via
   *  zustand → localStorage by the host component. */
  sidebarWidth: number;
  artifactsWidth: number;
  /** In-memory task list per session (Phase 9.5 — Plan / Tasks). */
  tasksBySession: Record<string, TaskItem[]>;
  /** URL the AI has asked us to preview via `open_preview` tool. */
  previewUrl: string | null;
  theme: Theme;
  askPermissions: boolean;
  permissionMode: PermissionMode;

  // Chat streaming (Phase 6)
  messagesBySession: Record<string, Message[]>;
  streamingBySession: Record<string, boolean>;
  streamingDraftBySession: Record<string, string>;
  streamingToolsBySession: Record<string, Array<{ id: string; name: string; input: Record<string, unknown>; result?: { ok: boolean; output?: unknown; error?: string } }>>;

  // User-facing chat draft (shared between ChatInput, mic, attach, etc.)
  chatDraft: string;
  setChatDraft: (text: string) => void;
  appendChatDraft: (text: string) => void;

  // Settings overlay
  settingsOpen: boolean;
  settingsSection: SettingsSection;
  providers: ProviderInfo[];
  providersLoading: boolean;

  // Actions
  init: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  refreshSessions: (projectId: string) => Promise<void>;
  refreshDatasets: (projectId: string) => Promise<void>;

  createProject: (name: string) => Promise<Project>;
  renameProject: (id: string, name: string) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  setActiveProject: (id: string | null) => Promise<void>;

  createSession: (projectId: string, title?: string) => Promise<Session>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  setActiveSession: (sessionId: string | null) => Promise<void>;

  uploadDataset: (
    projectId: string,
    file: File,
    onProgress?: (pct: number) => void,
  ) => Promise<Dataset>;
  deleteDataset: (datasetId: string) => Promise<void>;
  setActiveDataset: (datasetId: string | null) => void;

  setSidebarTab: (tab: SidebarTab) => void;
  toggleArtifacts: () => void;
  setArtifactsOpen: (open: boolean) => void;
  setActiveReport: (id: string | null, title?: string | null) => void;
  setRightPaneMode: (mode: RightPaneMode) => void;
  setPreviewUrl: (url: string | null) => void;
  setSidebarWidth: (w: number) => void;
  setArtifactsWidth: (w: number) => void;
  // Tasks (Plan / Tasks panel)
  addTask: (sessionId: string, title: string) => void;
  updateTask: (sessionId: string, id: string, patch: Partial<TaskItem>) => void;
  removeTask: (sessionId: string, id: string) => void;
  clearDoneTasks: (sessionId: string) => void;
  setTheme: (theme: Theme) => void;
  setAskPermissions: (v: boolean) => void;
  setPermissionMode: (mode: PermissionMode) => void;

  // Settings
  openSettings: (section?: SettingsSection) => void;
  closeSettings: () => void;
  setSettingsSection: (section: SettingsSection) => void;
  refreshProviders: () => Promise<void>;
  saveProviderKey: (name: string, apiKey: string) => Promise<void>;
  deleteProviderKey: (name: string) => Promise<void>;
  updateOllamaBaseUrl: (baseUrl: string) => Promise<void>;
  updateSessionModel: (
    sessionId: string,
    provider: string,
    model: string,
  ) => Promise<void>;

  // Chat streaming (Phase 6)
  loadMessages: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, text: string) => void;
  cancelStream: (sessionId: string) => void;

  // ChatGPT subscription OAuth
  startChatGPTAuth: () => Promise<{ flow_id: string; authorize_url: string }>;
  pollChatGPTAuth: (
    flowId: string,
  ) => Promise<
    | { status: 'pending'; error: null }
    | { status: 'complete'; error: null }
    | { status: 'error'; error: string }
    | { status: 'expired'; error?: null }
  >;
  signOutChatGPT: () => Promise<void>;
}

function toMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export const useAppStore = create<AppStore>((set, get) => ({
  projects: [],
  sessionsByProject: {},
  datasetsByProject: {},
  activeProjectId: null,
  activeSessionId: null,
  activeDatasetId: null,
  ready: false,
  error: null,

  sidebarTab: 'code',
  artifactsOpen: false,
  activeReportId: null,
  activeReportTitle: null,
  rightPaneMode: null,
  // Width state — read from localStorage on init so the user's last
  // layout sticks across reloads.
  sidebarWidth: (() => {
    if (typeof window === 'undefined') return 280;
    const v = parseInt(localStorage.getItem('stratforge.sidebarWidth') || '', 10);
    return Number.isFinite(v) && v >= 220 && v <= 600 ? v : 280;
  })(),
  artifactsWidth: (() => {
    if (typeof window === 'undefined') return 440;
    const v = parseInt(localStorage.getItem('stratforge.artifactsWidth') || '', 10);
    return Number.isFinite(v) && v >= 320 && v <= 900 ? v : 440;
  })(),
  tasksBySession: {},
  previewUrl: null,
  theme: 'dark',
  askPermissions: true,
  permissionMode: 'accept-edits',

  messagesBySession: {},
  streamingBySession: {},
  streamingDraftBySession: {},
  streamingToolsBySession: {},

  chatDraft: '',
  setChatDraft: (text) => set({ chatDraft: text }),
  appendChatDraft: (text) =>
    set((s) => ({ chatDraft: s.chatDraft ? `${s.chatDraft} ${text}` : text })),

  settingsOpen: false,
  settingsSection: 'providers',
  providers: [],
  providersLoading: false,

  init: async () => {
    try {
      const [projects, state, providers] = await Promise.all([
        listProjects(),
        getAppState(),
        listProviders().catch(() => [] as ProviderInfo[]),
      ]);
      // Fetch sessions + datasets for every project in parallel so the tree is ready up-front.
      const perProject = await Promise.all(
        projects.map(async (p) => {
          const [sessions, datasets] = await Promise.all([
            listSessions(p.id).catch(() => [] as Session[]),
            listDatasets(p.id).catch(() => [] as Dataset[]),
          ]);
          return [p.id, sessions, datasets] as const;
        }),
      );
      const sessionsByProject: Record<string, Session[]> = {};
      const datasetsByProject: Record<string, Dataset[]> = {};
      for (const [pid, s, d] of perProject) {
        sessionsByProject[pid] = s;
        datasetsByProject[pid] = d;
      }

      set({
        projects,
        sessionsByProject,
        datasetsByProject,
        providers,
        activeProjectId: state.active_project_id,
        activeSessionId: state.active_session_id,
        ready: true,
        error: null,
      });
    } catch (err) {
      set({ ready: true, error: toMessage(err) });
    }
  },

  refreshProjects: async () => {
    try {
      const projects = await listProjects();
      set({ projects, error: null });
    } catch (err) {
      set({ error: toMessage(err) });
    }
  },

  refreshSessions: async (projectId: string) => {
    try {
      const s = await listSessions(projectId);
      set((st) => ({
        sessionsByProject: { ...st.sessionsByProject, [projectId]: s },
      }));
    } catch (err) {
      set({ error: toMessage(err) });
    }
  },

  refreshDatasets: async (projectId: string) => {
    try {
      const d = await listDatasets(projectId);
      set((st) => ({
        datasetsByProject: { ...st.datasetsByProject, [projectId]: d },
      }));
    } catch (err) {
      set({ error: toMessage(err) });
    }
  },

  createProject: async (name: string) => {
    const project = await apiCreateProject(name);
    set((s) => ({
      projects: [project, ...s.projects],
      sessionsByProject: { ...s.sessionsByProject, [project.id]: [] },
      datasetsByProject: { ...s.datasetsByProject, [project.id]: [] },
    }));
    await get().setActiveProject(project.id);
    return project;
  },

  renameProject: async (id: string, name: string) => {
    const updated = await apiRenameProject(id, name);
    set((s) => ({
      projects: s.projects.map((p) => (p.id === id ? updated : p)),
    }));
  },

  deleteProject: async (id: string) => {
    await apiDeleteProject(id);
    set((s) => {
      const { [id]: _removedSess, ...restSess } = s.sessionsByProject;
      const { [id]: _removedData, ...restData } = s.datasetsByProject;
      const activeDatasetBelonged =
        s.activeDatasetId != null &&
        (s.datasetsByProject[id] ?? []).some(
          (d) => d.id === s.activeDatasetId,
        );
      return {
        projects: s.projects.filter((p) => p.id !== id),
        sessionsByProject: restSess,
        datasetsByProject: restData,
        activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
        activeSessionId:
          s.activeProjectId === id ? null : s.activeSessionId,
        activeDatasetId: activeDatasetBelonged ? null : s.activeDatasetId,
      };
    });
  },

  setActiveProject: async (id: string | null) => {
    // When switching projects, clear active session + dataset (session is also server-enforced).
    const state = get();
    const keep = id === state.activeProjectId;
    const nextSession = keep ? state.activeSessionId : null;
    const nextDataset = keep ? state.activeDatasetId : null;
    await setAppState({
      active_project_id: id,
      active_session_id: nextSession,
    });
    set({
      activeProjectId: id,
      activeSessionId: nextSession,
      activeDatasetId: nextDataset,
    });
  },

  createSession: async (projectId: string, title = 'New session') => {
    const session = await apiCreateSession(projectId, title);
    set((s) => ({
      sessionsByProject: {
        ...s.sessionsByProject,
        [projectId]: [session, ...(s.sessionsByProject[projectId] ?? [])],
      },
    }));
    await get().setActiveSession(session.id);
    return session;
  },

  renameSession: async (sessionId: string, title: string) => {
    const updated = await apiRenameSession(sessionId, title);
    set((s) => {
      const list = s.sessionsByProject[updated.project_id] ?? [];
      return {
        sessionsByProject: {
          ...s.sessionsByProject,
          [updated.project_id]: list.map((x) =>
            x.id === sessionId ? updated : x,
          ),
        },
      };
    });
  },

  deleteSession: async (sessionId: string) => {
    await apiDeleteSession(sessionId);
    set((s) => {
      const next: Record<string, Session[]> = {};
      for (const [pid, list] of Object.entries(s.sessionsByProject)) {
        next[pid] = list.filter((x) => x.id !== sessionId);
      }
      return {
        sessionsByProject: next,
        activeSessionId: s.activeSessionId === sessionId ? null : s.activeSessionId,
      };
    });
  },

  setActiveSession: async (sessionId: string | null) => {
    const state = get();
    // Find the project the session belongs to so we can keep active_project_id in sync.
    let projectId: string | null = state.activeProjectId;
    if (sessionId) {
      for (const [pid, list] of Object.entries(state.sessionsByProject)) {
        if (list.some((x) => x.id === sessionId)) {
          projectId = pid;
          break;
        }
      }
    }
    await setAppState({
      active_project_id: projectId,
      active_session_id: sessionId,
    });
    set({ activeProjectId: projectId, activeSessionId: sessionId });
  },

  uploadDataset: async (projectId, file, onProgress) => {
    const dataset = await apiUploadDataset(projectId, file, onProgress);
    set((s) => ({
      datasetsByProject: {
        ...s.datasetsByProject,
        [projectId]: [dataset, ...(s.datasetsByProject[projectId] ?? [])],
      },
      // Auto-activate newly uploaded dataset if none was picked.
      activeDatasetId: s.activeDatasetId ?? dataset.id,
    }));
    return dataset;
  },

  deleteDataset: async (datasetId: string) => {
    await apiDeleteDataset(datasetId);
    set((s) => {
      const next: Record<string, Dataset[]> = {};
      for (const [pid, list] of Object.entries(s.datasetsByProject)) {
        next[pid] = list.filter((d) => d.id !== datasetId);
      }
      return {
        datasetsByProject: next,
        activeDatasetId:
          s.activeDatasetId === datasetId ? null : s.activeDatasetId,
      };
    });
  },

  setActiveDataset: (datasetId: string | null) =>
    set({ activeDatasetId: datasetId }),

  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  toggleArtifacts: () => set((s) => ({ artifactsOpen: !s.artifactsOpen })),
  setArtifactsOpen: (open) => set({ artifactsOpen: open }),
  setActiveReport: (id, title = null) =>
    set({ activeReportId: id, activeReportTitle: title, artifactsOpen: id !== null }),
  setRightPaneMode: (mode) => set({ rightPaneMode: mode, artifactsOpen: mode !== null || get().activeReportId !== null }),
  setPreviewUrl: (url) => {
    if (url) {
      set({ previewUrl: url, rightPaneMode: 'preview', artifactsOpen: true });
    } else {
      set({ previewUrl: null });
    }
  },
  setSidebarWidth: (w) => {
    const clamped = Math.max(220, Math.min(600, Math.round(w)));
    if (typeof window !== 'undefined') {
      try { localStorage.setItem('stratforge.sidebarWidth', String(clamped)); } catch { /* quota */ }
    }
    set({ sidebarWidth: clamped });
  },
  setArtifactsWidth: (w) => {
    const clamped = Math.max(320, Math.min(900, Math.round(w)));
    if (typeof window !== 'undefined') {
      try { localStorage.setItem('stratforge.artifactsWidth', String(clamped)); } catch { /* quota */ }
    }
    set({ artifactsWidth: clamped });
  },

  addTask: (sessionId, title) =>
    set((s) => {
      const list = s.tasksBySession[sessionId] ?? [];
      const t: TaskItem = {
        id: `t_${Math.random().toString(36).slice(2, 10)}`,
        title: title.trim(),
        status: 'pending',
        created_at: new Date().toISOString(),
      };
      return { tasksBySession: { ...s.tasksBySession, [sessionId]: [...list, t] } };
    }),
  updateTask: (sessionId, id, patch) =>
    set((s) => {
      const list = s.tasksBySession[sessionId] ?? [];
      return {
        tasksBySession: {
          ...s.tasksBySession,
          [sessionId]: list.map((t) => (t.id === id ? { ...t, ...patch } : t)),
        },
      };
    }),
  removeTask: (sessionId, id) =>
    set((s) => ({
      tasksBySession: {
        ...s.tasksBySession,
        [sessionId]: (s.tasksBySession[sessionId] ?? []).filter((t) => t.id !== id),
      },
    })),
  clearDoneTasks: (sessionId) =>
    set((s) => ({
      tasksBySession: {
        ...s.tasksBySession,
        [sessionId]: (s.tasksBySession[sessionId] ?? []).filter((t) => t.status !== 'done'),
      },
    })),
  setTheme: (theme) => set({ theme }),
  setAskPermissions: (v) => set({ askPermissions: v }),
  setPermissionMode: (mode) => set({ permissionMode: mode, askPermissions: mode === 'ask' }),

  // ---------- Settings ----------
  openSettings: (section?: SettingsSection) => {
    set((s) => ({
      settingsOpen: true,
      settingsSection: section ?? s.settingsSection,
    }));
    // Fire-and-forget refresh when opening; keeps last-good data on failure.
    get().refreshProviders();
  },
  closeSettings: () => set({ settingsOpen: false }),
  setSettingsSection: (section) => set({ settingsSection: section }),

  refreshProviders: async () => {
    set({ providersLoading: true });
    try {
      const providers = await listProviders();
      set({ providers, providersLoading: false, error: null });
    } catch (err) {
      set({ providersLoading: false, error: toMessage(err) });
    }
  },

  saveProviderKey: async (name, apiKey) => {
    const updated = await apiSaveProviderKey(name, apiKey);
    set((s) => ({
      providers: s.providers.map((p) => (p.name === name ? updated : p)),
    }));
  },

  deleteProviderKey: async (name) => {
    await apiDeleteProviderKey(name);
    set((s) => ({
      providers: s.providers.map((p) =>
        p.name === name ? { ...p, has_credential: false } : p,
      ),
    }));
  },

  updateOllamaBaseUrl: async (baseUrl) => {
    const updated = await apiUpdateOllamaBaseUrl(baseUrl);
    set((s) => ({
      providers: s.providers.map((p) =>
        p.name === 'ollama' ? updated : p,
      ),
    }));
  },

  updateSessionModel: async (sessionId, provider, model) => {
    const updated = await apiUpdateSessionModel(sessionId, provider, model);
    set((s) => {
      const next: Record<string, Session[]> = {};
      for (const [pid, list] of Object.entries(s.sessionsByProject)) {
        next[pid] = list.map((x) => (x.id === sessionId ? updated : x));
      }
      return { sessionsByProject: next };
    });
  },

  // ---------- Chat streaming (Phase 6) ----------
  loadMessages: async (sessionId) => {
    // Clear any report carried over from a previous session — we'll
    // restore the latest one for THIS session below if one exists.
    set({ activeReportId: null, activeReportTitle: null });
    try {
      const msgs = await listSessionMessages(sessionId);
      set((s) => ({
        messagesBySession: { ...s.messagesBySession, [sessionId]: msgs },
      }));
      // After loading history, surface the most recent rendered report so
      // the artifacts panel auto-restores even for sessions that ran the
      // pipeline before the panel was wired. The scan logic lives in
      // `lib/artifactCommands` so the chat-input interceptor can reuse it.
      const foundReport = findLatestReportInMessages(msgs);
      if (foundReport) {
        set({
          activeReportId: foundReport.id,
          activeReportTitle: foundReport.title,
          artifactsOpen: true,
        });
      }
    } catch { /* ignore */ }
  },

  sendMessage: (sessionId, text) => {
    // ---- Artifact-open intent interceptor (Layer 1) -------------------
    // If the user is asking us to surface an existing report ("show
    // artifact", "report dikha", a literal `rp_<id>`, …), flip the
    // panel state synchronously *before* the LLM round-trip so it feels
    // instant. We still forward the message to the model so it can
    // narrate / answer follow-ups — we just don't wait on it for the
    // open action. If no matching report exists in history, we fall
    // through silently and let the model handle it normally.
    try {
      const intent = classifyArtifactIntent(text);
      if (intent.open) {
        const msgs = get().messagesBySession[sessionId] ?? [];
        let target: { id: string; title: string | null } | null = null;
        if (intent.explicitId) {
          // User typed a specific id. Try to pull a friendly title from
          // history, but open by id even if we can't.
          const fromHistory = findLatestReportInMessages(
            msgs.filter((m) =>
              m.content.some((b) =>
                b.type === 'tool_result' &&
                typeof (b as { content?: unknown }).content === 'string' &&
                ((b as { content?: string }).content ?? '').includes(intent.explicitId!),
              ),
            ),
          );
          target = {
            id: intent.explicitId,
            title: fromHistory?.title ?? null,
          };
        } else {
          target = findLatestReportInMessages(msgs);
        }
        if (target) {
          set({
            activeReportId: target.id,
            activeReportTitle: target.title,
            artifactsOpen: true,
          });
        }
      }
    } catch { /* never block send on intent parsing */ }
    // -------------------------------------------------------------------

    // Auto-rename session if it's the first message
    const currentMsgs = get().messagesBySession[sessionId] ?? [];
    if (currentMsgs.length === 0) {
      const isVoice = text.startsWith('🎤 ');
      let cleanText = isVoice ? text.replace('🎤 ', '') : text;
      cleanText = cleanText.replace(/```[\s\S]*?```/g, '').trim();
      if (!cleanText && text) cleanText = "Code snippet";
      const newTitle = cleanText.length > 35 ? cleanText.slice(0, 35) + '...' : cleanText;
      if (newTitle) {
        get().renameSession(sessionId, newTitle).catch(() => {});
      }
    }

    const stream = openSessionStream(sessionId);
    set((s) => ({
      streamingBySession: { ...s.streamingBySession, [sessionId]: true },
      streamingDraftBySession: { ...s.streamingDraftBySession, [sessionId]: '' },
      streamingToolsBySession: { ...s.streamingToolsBySession, [sessionId]: [] },
    }));

    // Store the close function so cancelStream can use it
    const closeRef = { current: stream.close };
    (window as unknown as Record<string, unknown>)[`__ws_${sessionId}`] = closeRef;

    stream.onFrame((frame) => {
      const st = get();
      if (frame.type === 'user') {
        const msgs = st.messagesBySession[sessionId] ?? [];
        set({ messagesBySession: { ...st.messagesBySession, [sessionId]: [...msgs, frame.message] } });
      } else if (frame.type === 'text') {
        const draft = (st.streamingDraftBySession[sessionId] ?? '') + frame.delta;
        set({ streamingDraftBySession: { ...st.streamingDraftBySession, [sessionId]: draft } });
      } else if (frame.type === 'tool_use') {
        const tools = [...(st.streamingToolsBySession[sessionId] ?? []), { id: frame.id, name: frame.name, input: frame.input }];
        set({ streamingToolsBySession: { ...st.streamingToolsBySession, [sessionId]: tools } });
      } else if (frame.type === 'tool_result') {
        const tools = (st.streamingToolsBySession[sessionId] ?? []).map((t) =>
          t.id === frame.tool_use_id ? { ...t, result: { ok: frame.ok, output: frame.output, error: frame.error } } : t
        );
        set({ streamingToolsBySession: { ...st.streamingToolsBySession, [sessionId]: tools } });
        // Auto-open the artifacts panel for any tool result that produced
        // a report. Today this is `render_report` — but we key on the
        // shape of the output (presence of `report_id`) so future tools
        // that emit reports plug in for free.
        if (frame.ok && frame.output && typeof frame.output === 'object') {
          const out = frame.output as Record<string, unknown>;
          const rid = typeof out.report_id === 'string' ? out.report_id : null;
          if (rid) {
            const title = typeof out.title === 'string' ? out.title : null;
            set({
              activeReportId: rid,
              activeReportTitle: title,
              artifactsOpen: true,
            });
          }
          // Auto-open preview when AI calls `open_preview` tool
          if (out.action === 'open_preview' && typeof out.url === 'string') {
            get().setPreviewUrl(out.url as string);
          }
          // Auto-open preview when AI starts a process with a detected port
          if (typeof out.preview_url === 'string') {
            get().setPreviewUrl(out.preview_url as string);
          }
        }
      } else if (frame.type === 'message') {
        const msgs = st.messagesBySession[sessionId] ?? [];
        set({ messagesBySession: { ...st.messagesBySession, [sessionId]: [...msgs, frame.message] } });
      } else if (frame.type === 'done') {
        set({
          streamingBySession: { ...st.streamingBySession, [sessionId]: false },
          streamingDraftBySession: { ...st.streamingDraftBySession, [sessionId]: '' },
          streamingToolsBySession: { ...st.streamingToolsBySession, [sessionId]: [] },
        });
        stream.close();
      } else if (frame.type === 'error') {
        // Surface server / provider errors instead of silent close. Toast
        // for immediate visibility + inline error bubble in the chat so
        // it survives the user scrolling away.
        const msg = frame.message || 'Provider error';
        set({
          streamingBySession: { ...st.streamingBySession, [sessionId]: false },
          streamingDraftBySession: { ...st.streamingDraftBySession, [sessionId]: '' },
        });
        // Emit a synthetic system-error message so the user can see what
        // happened (rate-limit, no key, network, etc.). Negative id keeps
        // it out of the way of real persisted message ids.
        const errMsg: Message = {
          id: -Date.now(),
          session_id: sessionId,
          role: 'assistant',
          content: [{ type: 'text', text: `**⚠️ Error**\n\n${msg}` }],
          created_at: new Date().toISOString(),
        };
        const msgs = st.messagesBySession[sessionId] ?? [];
        set({
          messagesBySession: { ...st.messagesBySession, [sessionId]: [...msgs, errMsg] },
        });
        // Toast for ambient awareness — async import to avoid pulling Toast
        // into the store's hot module list.
        import('../components/ui/Toast').then(({ toast }) => toast(msg)).catch(() => undefined);
        stream.close();
      }
    });

    stream.ready
      .then(() =>
        stream.send(text, {
          permissionMode: get().permissionMode,
          datasetId: get().activeDatasetId,
        }),
      )
      .catch(() => {
        set((s) => ({ streamingBySession: { ...s.streamingBySession, [sessionId]: false } }));
      });
  },

  cancelStream: (sessionId) => {
    const ref = (window as unknown as Record<string, unknown>)[`__ws_${sessionId}`] as { current: () => void } | undefined;
    ref?.current();
    set((s) => ({
      streamingBySession: { ...s.streamingBySession, [sessionId]: false },
      streamingDraftBySession: { ...s.streamingDraftBySession, [sessionId]: '' },
    }));
  },

  // ---------- ChatGPT subscription OAuth ----------
  startChatGPTAuth: async () => {
    return await apiStartChatGPTAuth();
  },

  pollChatGPTAuth: async (flowId) => {
    return await apiPollChatGPTAuth(flowId);
  },

  signOutChatGPT: async () => {
    await apiSignOutChatGPT();
    await get().refreshProviders();
  },
}));

// ---------- Selector hooks ----------

export const useActiveProject = (): Project | null =>
  useAppStore((s) => {
    if (!s.activeProjectId) return null;
    return s.projects.find((p) => p.id === s.activeProjectId) ?? null;
  });

export const useActiveSession = (): Session | null =>
  useAppStore((s) => {
    if (!s.activeSessionId) return null;
    for (const list of Object.values(s.sessionsByProject)) {
      const found = list.find((x) => x.id === s.activeSessionId);
      if (found) return found;
    }
    return null;
  });

export const useActiveDataset = (): Dataset | null =>
  useAppStore((s) => {
    if (!s.activeDatasetId) return null;
    for (const list of Object.values(s.datasetsByProject)) {
      const found = list.find((x) => x.id === s.activeDatasetId);
      if (found) return found;
    }
    return null;
  });
