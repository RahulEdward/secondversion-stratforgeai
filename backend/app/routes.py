import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import json as _json

from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import __version__, secrets, storage
from . import orchestrator
from .data import DataError, load_dataset, preview_dataset
from .indicators import IndicatorError, compute as compute_indicator
from .providers import PROVIDER_NAMES, get_provider, provider_info
from .providers.base import ProviderError
from .providers.ollama_p import OllamaProvider
from .tools import all_tools
from .schemas import (
    AppState,
    Dataset,
    DatasetPreview,
    ModelInfoDTO,
    OllamaConfigPayload,
    Project,
    ProjectCreate,
    ProjectUpdate,
    ProviderInfo,
    ProviderKeyPayload,
    Session,
    SessionCreate,
    SessionModelUpdate,
    SessionUpdate,
)

router = APIRouter()


# ---------- Health ----------


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# ---------- Projects ----------


@router.get("/projects", response_model=List[Project])
def list_projects() -> List[Project]:
    return storage.list_projects()


@router.post(
    "/projects",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
)
def create_project(payload: ProjectCreate) -> Project:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    return storage.create_project(name)


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=Project)
def rename_project(project_id: str, payload: ProjectUpdate) -> Project:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    project = storage.rename_project(project_id, name)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project(project_id: str) -> None:
    if not storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


# ---------- Sessions ----------


@router.get(
    "/projects/{project_id}/sessions",
    response_model=List[Session],
)
def list_sessions(project_id: str) -> List[Session]:
    sessions = storage.list_sessions(project_id)
    if sessions is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return sessions


@router.post(
    "/projects/{project_id}/sessions",
    response_model=Session,
    status_code=status.HTTP_201_CREATED,
)
def create_session(project_id: str, payload: SessionCreate) -> Session:
    title = payload.title.strip() or "New session"
    session = storage.create_session(project_id, title)
    if session is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return session


@router.get("/sessions/{session_id}", response_model=Session)
def get_session(session_id: str) -> Session:
    session = storage.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/sessions/{session_id}", response_model=Session)
def rename_session(session_id: str, payload: SessionUpdate) -> Session:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    session = storage.rename_session(session_id, title)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str) -> None:
    if not storage.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")


# ---------- Datasets ----------

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}


@router.get(
    "/projects/{project_id}/datasets",
    response_model=List[Dataset],
)
def list_datasets(project_id: str) -> List[Dataset]:
    datasets = storage.list_datasets(project_id)
    if datasets is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return datasets


@router.post(
    "/projects/{project_id}/datasets",
    response_model=Dataset,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset(project_id: str, file: UploadFile) -> Dataset:
    if storage.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}"
            ),
        )

    # Stream to a temp file so pandas can read it with path-based APIs.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    total = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                )
            tmp.write(chunk)
        tmp.close()

        try:
            dataset = storage.ingest_and_store_dataset(
                project_id, filename, Path(tmp.name)
            )
        except DataError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass

    if dataset is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return dataset


@router.get("/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(dataset_id: str) -> Dataset:
    dataset = storage.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get(
    "/datasets/{dataset_id}/preview",
    response_model=DatasetPreview,
)
def dataset_preview(dataset_id: str, rows: int = 50) -> DatasetPreview:
    dataset = storage.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    rows = max(1, min(rows, 500))
    path = storage.dataset_path(dataset.project_id, dataset.id)
    sample = preview_dataset(path, rows)
    return DatasetPreview(
        id=dataset.id,
        filename=dataset.filename,
        columns=dataset.columns,
        rows=dataset.rows,
        sample=sample,
    )


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset(dataset_id: str) -> None:
    if not storage.delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")


# ---------- Indicators ----------

# How many bars from the tail we return by default — keeps payloads small.
DEFAULT_INDICATOR_TAIL = 500


def _float_safe(value: float) -> Optional[float]:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return float(value)


@router.get("/tools")
def list_tools() -> Dict[str, Any]:
    """List all tool schemas the AI orchestrator can call."""
    return {"tools": all_tools()}


@router.post("/datasets/{dataset_id}/indicators")
def compute_dataset_indicator(
    dataset_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Compute an indicator on a stored dataset.

    Body: {"indicator": "rsi", "params": {"period": 14}, "tail": 500}
    """
    dataset = storage.get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    indicator_name = payload.get("indicator")
    if not indicator_name or not isinstance(indicator_name, str):
        raise HTTPException(status_code=400, detail="Missing 'indicator' name")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="'params' must be an object")
    tail = int(payload.get("tail", DEFAULT_INDICATOR_TAIL))
    tail = max(1, min(tail, 5000))

    path = storage.dataset_path(dataset.project_id, dataset.id)
    df = load_dataset(path)

    try:
        result = compute_indicator(df, indicator_name, params)
    except IndicatorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Slice to tail and align with timestamps when available.
    result = result.tail(tail)
    if "time" in df.columns:
        times = df["time"].iloc[-len(result):].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
    else:
        times = [str(i) for i in result.index.tolist()]

    series: Dict[str, List[Optional[float]]] = {}
    for col in result.columns:
        series[str(col)] = [_float_safe(v) for v in result[col].tolist()]

    return {
        "indicator": indicator_name,
        "params": params,
        "dataset_id": dataset_id,
        "times": times,
        "series": series,
        "rows": len(result),
    }


# ---------- Providers (Phase 4) ----------


@router.get("/settings/providers", response_model=List[ProviderInfo])
async def list_providers() -> List[ProviderInfo]:
    """Return all known providers with credential + reachability status."""
    out: List[ProviderInfo] = []
    for name in PROVIDER_NAMES:
        info = await provider_info(name)
        if info is None:
            continue
        out.append(
            ProviderInfo(
                name=info.name,
                kind=info.kind,
                label=info.label,
                has_credential=info.has_credential,
                reachable=info.reachable,
                error=info.error,
                extra=info.extra,
            )
        )
    return out


def _reject_ollama_key(provider_name: str) -> None:
    """Ollama uses `base_url` via a dedicated endpoint — not an API key."""
    if provider_name == OllamaProvider.name:
        raise HTTPException(
            status_code=400,
            detail="Ollama is configured via /settings/providers/ollama/base_url",
        )


@router.post(
    "/settings/providers/{provider_name}/key",
    response_model=ProviderInfo,
)
async def save_provider_key(
    provider_name: str, payload: ProviderKeyPayload
) -> ProviderInfo:
    provider = get_provider(provider_name)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    _reject_ollama_key(provider_name)
    key = payload.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    secrets.set_key(provider_name, key)
    info = await provider_info(provider_name)
    assert info is not None
    return ProviderInfo(**info.__dict__)


@router.delete(
    "/settings/providers/{provider_name}/key",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_provider_key(provider_name: str) -> None:
    if get_provider(provider_name) is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    _reject_ollama_key(provider_name)
    removed = secrets.delete_key(provider_name)
    if not removed:
        raise HTTPException(status_code=404, detail="No key stored")


@router.put(
    "/settings/providers/ollama/base_url",
    response_model=ProviderInfo,
)
async def set_ollama_base_url(payload: OllamaConfigPayload) -> ProviderInfo:
    url = payload.base_url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="base_url must start with http(s)://")
    # Reuse the same secret store for Ollama's URL — it's not secret but living
    # alongside other credentials keeps config in one place.
    secrets.set_key(OllamaProvider.name, url)
    info = await provider_info(OllamaProvider.name)
    assert info is not None
    return ProviderInfo(**info.__dict__)


@router.get(
    "/settings/providers/{provider_name}/models",
    response_model=List[ModelInfoDTO],
)
async def list_provider_models(provider_name: str) -> List[ModelInfoDTO]:
    provider = get_provider(provider_name)
    if provider is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    try:
        models = await provider.list_models()
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        ModelInfoDTO(
            id=m.id,
            label=m.label,
            context_window=m.context_window,
            description=m.description,
        )
        for m in models
    ]


@router.patch("/sessions/{session_id}/model", response_model=Session)
def set_session_model(session_id: str, payload: SessionModelUpdate) -> Session:
    if get_provider(payload.provider) is None:
        raise HTTPException(status_code=400, detail="Unknown provider")
    updated = storage.update_session_model(
        session_id, payload.provider, payload.model
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


# ---------- App state ----------


@router.get("/app/state", response_model=AppState)
def get_app_state() -> AppState:
    return storage.load_app_state()


@router.put("/app/state", response_model=AppState)
def set_app_state(state: AppState) -> AppState:
    if state.active_project_id is not None:
        if storage.get_project(state.active_project_id) is None:
            raise HTTPException(
                status_code=404, detail="Active project does not exist"
            )
    if state.active_session_id is not None:
        session = storage.get_session(state.active_session_id)
        if session is None:
            raise HTTPException(
                status_code=404, detail="Active session does not exist"
            )
        if (
            state.active_project_id is not None
            and session.project_id != state.active_project_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Active session does not belong to active project",
            )
    storage.save_app_state(state)
    return state


# ---------- Agent tool proxy (Files / Diff / Terminal panels) ----------


@router.post("/agent/tool")
async def run_agent_tool_endpoint(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Thin REST proxy over a single agent-tool dispatch. Used by the
    Claude Code-style right-pane panels (Files / Diff / Terminal)."""
    name = str(payload.get("name") or "")
    if not name:
        raise HTTPException(400, "Missing `name`")
    inputs = payload.get("input") or {}
    if not isinstance(inputs, dict):
        raise HTTPException(400, "`input` must be an object")
    mode = str(payload.get("permission_mode") or "plan")
    if mode not in {"ask", "accept-edits", "plan", "bypass"}:
        mode = "plan"

    from .tool_exec import run_tool

    return await run_tool(name, inputs, permission_mode=mode)


# ---------- Memory (Phase 9) — per-project durable learnings ----------


@router.get("/projects/{project_id}/memory")
def list_project_memory(project_id: str) -> List[Dict[str, Any]]:
    if storage.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    from .memory import list_memories

    entries = list_memories(project_id)
    return [
        {
            "name": e.name, "title": e.title, "description": e.description,
            "type": e.type, "updated_at": e.updated_at,
            # body excluded from list view — fetched via the detail route.
        }
        for e in entries
    ]


@router.get("/projects/{project_id}/memory/{name}")
def get_project_memory(project_id: str, name: str) -> Dict[str, Any]:
    if storage.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    from .memory import read_memory

    entry = read_memory(project_id, name)
    if entry is None:
        raise HTTPException(404, "Memory entry not found")
    return {
        "name": entry.name, "title": entry.title, "description": entry.description,
        "type": entry.type, "updated_at": entry.updated_at, "body": entry.body,
    }


@router.put("/projects/{project_id}/memory/{name}")
def upsert_project_memory(project_id: str, name: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    if storage.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    from .memory import write_memory

    entry = write_memory(
        project_id,
        name=name,
        title=str(payload.get("title") or name),
        description=str(payload.get("description") or ""),
        body=str(payload.get("body") or ""),
        type=str(payload.get("type") or "reference"),
    )
    return {
        "name": entry.name, "title": entry.title, "description": entry.description,
        "type": entry.type, "updated_at": entry.updated_at, "body": entry.body,
    }


@router.delete(
    "/projects/{project_id}/memory/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_memory(project_id: str, name: str) -> None:
    if storage.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    from .memory import delete_memory

    if not delete_memory(project_id, name):
        raise HTTPException(404, "Memory entry not found")


# ---------- Reports (Phase 8) — serve rendered HTML + on-demand PDF ----------


# Cache the bundled Plotly JS in-process so we don't pay the disk read on every
# report load. The plotly python package ships its own copy of plotly.min.js,
# which means we don't need a CDN — useful for users on offline / firewalled
# networks where `cdn.plot.ly` is unreachable. ~4.5 MB string; harmless to keep.
_PLOTLY_JS_CACHE: Optional[str] = None


def _get_plotly_js() -> str:
    global _PLOTLY_JS_CACHE
    if _PLOTLY_JS_CACHE is None:
        from plotly.offline import get_plotlyjs

        _PLOTLY_JS_CACHE = get_plotlyjs()
    return _PLOTLY_JS_CACHE


@router.get("/assets/plotly.min.js")
def get_plotly_js() -> Response:
    """Serve the bundled Plotly runtime so report iframes never depend on a CDN.

    `Cache-Control: immutable` because the file is content-addressed by the
    plotly package version — clients can hold onto it indefinitely.
    """
    return Response(
        content=_get_plotly_js(),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


# NOTE on route order: the `.pdf` route MUST be registered before the
# bare `/reports/{report_id}` route. Starlette's default `{path}`
# converter accepts dots, so `/reports/rp_xxx.pdf` would otherwise be
# matched by `/reports/{report_id}` with `report_id='rp_xxx.pdf'` — the
# PDF handler would never run, and `find_report` would 404. This was
# the source of the "blank page on download" the artifacts pane showed.


@router.get("/reports/{report_id}.pdf")
def get_report_pdf(report_id: str) -> FileResponse:
    """Serve (and lazily render) the PDF. First request takes a few seconds.

    Implementation note: this is a sync `def` (not `async def`) on
    purpose. Playwright's async API uses `asyncio.create_subprocess_exec`,
    which raises `NotImplementedError` on Windows when running under
    uvicorn's default `SelectorEventLoop`. Letting FastAPI run us in its
    threadpool means we get a fresh loop per call where the sync
    Playwright wrapper (`export_pdf_sync` → `asyncio.run`) picks the
    Proactor policy and the subprocess works.
    """
    from .reports import export_pdf_sync, find_report, ReportNotFound

    found = find_report(report_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Report not found")
    project_id, _meta = found
    try:
        pdf_path = export_pdf_sync(project_id, report_id)
    except ReportNotFound:
        raise HTTPException(status_code=410, detail="Report HTML is gone")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"PDF render failed: {type(exc).__name__}: {exc}",
        )
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{report_id}.pdf",
    )


@router.get("/reports/{report_id}", response_class=HTMLResponse)
def get_report_html(report_id: str) -> HTMLResponse:
    """Serve the rendered HTML report. Used by the artifacts panel iframe."""
    from .reports import find_report, report_paths

    found = find_report(report_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Report not found")
    project_id, _meta = found
    html_path = report_paths(project_id, report_id)["html"]
    if not html_path.exists():
        raise HTTPException(
            status_code=410, detail="Report metadata exists but HTML is gone"
        )
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ---------- Messages + live chat stream (Phase 6) ----------


@router.get("/sessions/{session_id}/messages")
def list_session_messages(session_id: str) -> list:
    messages = storage.list_messages(session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return messages


@router.websocket("/sessions/{session_id}/stream")
async def session_stream(websocket: WebSocket, session_id: str) -> None:
    """Bidirectional chat stream.

    Client sends: {"text": "user message"}
    Server streams: orchestrator frames as JSON lines.
    """
    await websocket.accept()
    if storage.get_session(session_id) is None:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return
    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                return
            try:
                payload = _json.loads(raw)
            except _json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            text = (payload.get("text") or "").strip()
            if not text:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue
            mode = payload.get("permission_mode") or "accept-edits"
            if mode not in {"ask", "accept-edits", "plan", "bypass"}:
                mode = "accept-edits"
            dataset_id = payload.get("dataset_id") or None
            if dataset_id is not None and not isinstance(dataset_id, str):
                dataset_id = None
            try:
                async for frame in orchestrator.run_turn(
                    session_id,
                    text,
                    permission_mode=mode,
                    dataset_id=dataset_id,
                ):
                    await websocket.send_json(frame)
            except WebSocketDisconnect:
                return
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": f"Orchestrator error: {exc}"})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------- ChatGPT Subscription OAuth (OpenYak-style) ----------


@router.post("/auth/chatgpt/start")
async def start_chatgpt_auth() -> dict:
    """Start ChatGPT OAuth PKCE flow. Returns auth URL to open in browser."""
    from . import oauth_callback_server

    result = await oauth_callback_server.start_login()
    return {
        "flow_id": result["state"],
        "authorize_url": result["auth_url"],
    }


@router.get("/auth/chatgpt/status/{flow_id}")
def chatgpt_auth_status(flow_id: str) -> dict:
    """Poll the state of an in-progress ChatGPT flow."""
    from . import oauth_callback_server

    return oauth_callback_server.get_flow_status(flow_id)


@router.delete(
    "/auth/chatgpt/session",
    status_code=status.HTTP_204_NO_CONTENT,
)
def chatgpt_auth_signout() -> None:
    """Drop stored ChatGPT subscription tokens."""
    from . import oauth_callback_server

    oauth_callback_server.clear_tokens()
