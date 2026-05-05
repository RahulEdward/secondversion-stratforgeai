// Pick the backend URL:
// - VITE_WEB_ONLY=1  → same-origin (''), so Vite's dev proxy forwards /api to backend.
// - VITE_API_BASE_URL set → use that exact URL.
// - Otherwise         → 127.0.0.1:8765 (what the packaged Electron app talks to).
const WEB_ONLY = import.meta.env?.VITE_WEB_ONLY === '1';
const ENV_URL = import.meta.env?.VITE_API_BASE_URL as string | undefined;
const BASE_URL = WEB_ONLY
  ? ''
  : ENV_URL && ENV_URL.length > 0
    ? ENV_URL
    : 'http://127.0.0.1:8765';

export interface HealthResponse {
  status: string;
  version: string;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  default_provider: string | null;
}

export interface Session {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  provider: string | null;
  model: string | null;
}

export type ProviderKind = 'api_key' | 'local' | 'subscription';

export interface ProviderInfo {
  name: string;
  kind: ProviderKind;
  label: string;
  has_credential: boolean;
  reachable: boolean | null;
  error: string | null;
  extra: Record<string, string | number | boolean | null>;
}

export interface ProviderModel {
  id: string;
  label: string;
  context_window: number | null;
  description: string | null;
}

export interface AppStateDTO {
  active_project_id: string | null;
  active_session_id: string | null;
}

export interface Dataset {
  id: string;
  project_id: string;
  filename: string;
  rows: number;
  columns: string[];
  has_ohlcv: boolean;
  start_date: string | null;
  end_date: string | null;
  size_bytes: number;
  uploaded_at: string;
}

export type PreviewCell = string | number | boolean | null;

export interface DatasetPreview {
  id: string;
  filename: string;
  columns: string[];
  rows: number;
  sample: Record<string, PreviewCell>[];
}

export interface IndicatorResult {
  indicator: string;
  params: Record<string, unknown>;
  dataset_id: string;
  times: string[];
  series: Record<string, Array<number | null>>;
  rows: number;
}

export interface ToolSchema {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 5000,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new ApiError(response.status, text || response.statusText);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------- Health ----------

export async function pingBackend(): Promise<HealthResponse | null> {
  try {
    return await request<HealthResponse>('/api/health', undefined, 2000);
  } catch {
    return null;
  }
}

// ---------- Projects ----------

export async function listProjects(): Promise<Project[]> {
  return request<Project[]>('/api/projects');
}

export async function createProject(name: string): Promise<Project> {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function renameProject(
  id: string,
  name: string,
): Promise<Project> {
  return request<Project>(`/api/projects/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

export async function deleteProject(id: string): Promise<void> {
  await request<void>(`/api/projects/${id}`, { method: 'DELETE' });
}

// ---------- Sessions ----------

export async function listSessions(projectId: string): Promise<Session[]> {
  return request<Session[]>(`/api/projects/${projectId}/sessions`);
}

export async function createSession(
  projectId: string,
  title = 'New session',
): Promise<Session> {
  return request<Session>(`/api/projects/${projectId}/sessions`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function renameSession(
  sessionId: string,
  title: string,
): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request<void>(`/api/sessions/${sessionId}`, { method: 'DELETE' });
}

// ---------- Datasets ----------

export async function listDatasets(projectId: string): Promise<Dataset[]> {
  return request<Dataset[]>(`/api/projects/${projectId}/datasets`);
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  return request<Dataset>(`/api/datasets/${datasetId}`);
}

export async function getDatasetPreview(
  datasetId: string,
  rows = 50,
): Promise<DatasetPreview> {
  return request<DatasetPreview>(
    `/api/datasets/${datasetId}/preview?rows=${rows}`,
  );
}

export async function deleteDataset(datasetId: string): Promise<void> {
  await request<void>(`/api/datasets/${datasetId}`, { method: 'DELETE' });
}

/**
 * Multipart upload using XHR so we can surface progress events.
 * The FastAPI endpoint expects a single `file` field.
 */
export function uploadDataset(
  projectId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<Dataset> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE_URL}/api/projects/${projectId}/datasets`);

    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as Dataset);
        } catch (err) {
          reject(err);
        }
      } else {
        reject(
          new ApiError(xhr.status, xhr.responseText || xhr.statusText),
        );
      }
    };
    xhr.onerror = () => reject(new ApiError(0, 'Network error'));
    xhr.onabort = () => reject(new ApiError(0, 'Upload aborted'));

    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

// ---------- Indicators / tools ----------

export async function listTools(): Promise<ToolSchema[]> {
  const resp = await request<{ tools: ToolSchema[] }>('/api/tools');
  return resp.tools;
}

export async function computeIndicator(
  datasetId: string,
  indicator: string,
  params: Record<string, unknown> = {},
  tail = 500,
): Promise<IndicatorResult> {
  return request<IndicatorResult>(`/api/datasets/${datasetId}/indicators`, {
    method: 'POST',
    body: JSON.stringify({ indicator, params, tail }),
  });
}

// ---------- App state ----------

export async function getAppState(): Promise<AppStateDTO> {
  return request<AppStateDTO>('/api/app/state');
}

export async function setAppState(state: AppStateDTO): Promise<AppStateDTO> {
  return request<AppStateDTO>('/api/app/state', {
    method: 'PUT',
    body: JSON.stringify(state),
  });
}

// ---------- Providers (Phase 4) ----------

export async function listProviders(): Promise<ProviderInfo[]> {
  return request<ProviderInfo[]>('/api/settings/providers');
}

export async function saveProviderKey(
  name: string,
  apiKey: string,
): Promise<ProviderInfo> {
  return request<ProviderInfo>(`/api/settings/providers/${name}/key`, {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function deleteProviderKey(name: string): Promise<void> {
  await request<void>(`/api/settings/providers/${name}/key`, {
    method: 'DELETE',
  });
}

export async function updateOllamaBaseUrl(baseUrl: string): Promise<ProviderInfo> {
  return request<ProviderInfo>('/api/settings/providers/ollama/base_url', {
    method: 'PUT',
    body: JSON.stringify({ base_url: baseUrl }),
  });
}

export async function listProviderModels(name: string): Promise<ProviderModel[]> {
  return request<ProviderModel[]>(
    `/api/settings/providers/${name}/models`,
    undefined,
    10000,
  );
}

export async function updateSessionModel(
  sessionId: string,
  provider: string,
  model: string,
): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}/model`, {
    method: 'PATCH',
    body: JSON.stringify({ provider, model }),
  });
}

// ---------- Memory (Phase 9) ----------

export type MemoryType = 'user' | 'feedback' | 'project' | 'reference';

export interface MemorySummary {
  name: string;
  title: string;
  description: string;
  type: MemoryType;
  updated_at: string;
}

export interface MemoryEntry extends MemorySummary {
  body: string;
}

export async function listMemory(projectId: string): Promise<MemorySummary[]> {
  return request<MemorySummary[]>(`/api/projects/${projectId}/memory`);
}

export async function getMemory(projectId: string, name: string): Promise<MemoryEntry> {
  return request<MemoryEntry>(`/api/projects/${projectId}/memory/${encodeURIComponent(name)}`);
}

export async function upsertMemory(
  projectId: string,
  name: string,
  payload: { title: string; description: string; body: string; type: MemoryType },
): Promise<MemoryEntry> {
  return request<MemoryEntry>(`/api/projects/${projectId}/memory/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteMemory(projectId: string, name: string): Promise<void> {
  await request<void>(`/api/projects/${projectId}/memory/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
}

// ---------- Messages + live chat stream (Phase 6) ----------

export interface Message {
  id: number;
  session_id: string;
  role: string;
  content: Array<Record<string, unknown>>;
  created_at: string;
}

export type StreamFrame =
  | { type: 'user'; message: Message }
  | { type: 'text'; delta: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool_use_id: string; ok: boolean; output?: unknown; error?: string }
  | { type: 'message'; message: Message }
  | { type: 'done' }
  | { type: 'error'; message: string };

export async function listSessionMessages(sessionId: string): Promise<Message[]> {
  return request<Message[]>(`/api/sessions/${sessionId}/messages`);
}

const WS_BASE = WEB_ONLY
  ? `ws://${window.location.host}`
  : BASE_URL.replace(/^http/, 'ws');

export interface SendMessageOpts {
  permissionMode?: string;
  /** Active dataset id from the sidebar — passed through so the LLM has it
   *  in its system prompt without the user needing to type it. */
  datasetId?: string | null;
}

export function openSessionStream(sessionId: string): {
  send: (text: string, opts?: SendMessageOpts) => void;
  close: () => void;
  onFrame: (cb: (frame: StreamFrame) => void) => void;
  ready: Promise<void>;
} {
  const ws = new WebSocket(`${WS_BASE}/api/sessions/${sessionId}/stream`);
  let frameCb: ((frame: StreamFrame) => void) | null = null;

  const ready = new Promise<void>((resolve, reject) => {
    ws.onopen = () => resolve();
    ws.onerror = () => reject(new Error('WebSocket connection failed'));
  });

  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data) as StreamFrame;
      frameCb?.(frame);
    } catch { /* ignore parse errors */ }
  };

  ws.onclose = (e) => {
    // If the socket closes and it wasn't a normal 1000 closure,
    // synthesize an error so the frontend resets its `streaming` state
    // and unlocks the chat input box.
    if (e.code !== 1000) {
      frameCb?.({ type: 'error', message: 'Connection lost to AI engine.' });
    }
  };

  return {
    send: (text, opts) =>
      ws.send(
        JSON.stringify({
          text,
          permission_mode: opts?.permissionMode ?? 'accept-edits',
          dataset_id: opts?.datasetId ?? null,
        }),
      ),
    close: () => ws.close(),
    onFrame: (cb) => { frameCb = cb; },
    ready,
  };
}

// ---------- ChatGPT Subscription OAuth ----------

export interface ChatGPTAuthStart {
  flow_id: string;
  authorize_url: string;
}

export type ChatGPTAuthStatus =
  | { status: 'pending'; error: null }
  | { status: 'complete'; error: null }
  | { status: 'error'; error: string }
  | { status: 'expired'; error?: null };

export async function startChatGPTAuth(): Promise<ChatGPTAuthStart> {
  return request<ChatGPTAuthStart>('/api/auth/chatgpt/start', {
    method: 'POST',
  });
}

export async function pollChatGPTAuth(
  flowId: string,
): Promise<ChatGPTAuthStatus> {
  return request<ChatGPTAuthStatus>(
    `/api/auth/chatgpt/status/${flowId}`,
    undefined,
    8000,
  );
}

export async function signOutChatGPT(): Promise<void> {
  await fetch(`${BASE_URL}/api/auth/chatgpt/session`, { method: 'DELETE' });
}

export async function transcribeAudio(audioBlob: Blob): Promise<string> {
  const form = new FormData();
  form.append('file', audioBlob, 'audio.webm');
  
  const response = await fetch(`${BASE_URL}/api/agent/transcribe`, {
    method: 'POST',
    body: form,
  });
  
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new ApiError(response.status, text || response.statusText);
  }
  
  const data = await response.json();
  return data.text;
}


