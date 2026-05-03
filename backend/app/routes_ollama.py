"""``/api/ollama/*`` routes — binary setup, daemon lifecycle, model mgmt."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .ollama import get_manager
from .ollama.library import CATEGORIES, get_library as fetch_library

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class OllamaRuntimeStatus(BaseModel):
    binary_installed: bool = False
    running: bool = False
    port: int = 11434
    base_url: Optional[str] = None
    version: Optional[str] = None
    models_dir: Optional[str] = None
    disk_usage_bytes: int = 0


class ModelPullRequest(BaseModel):
    name: str  # e.g. "llama3.2:3b"


class ModelDeleteResponse(BaseModel):
    status: str
    name: str


class ModelWarmupRequest(BaseModel):
    model: str


# ── Helpers ───────────────────────────────────────────────────────────────


def _require_running() -> str:
    mgr = get_manager()
    if not mgr.is_running:
        raise HTTPException(
            status_code=400, detail="Ollama is not running — start it first"
        )
    return mgr.base_url


# ── Runtime endpoints ─────────────────────────────────────────────────────


@router.get("/ollama/status", response_model=OllamaRuntimeStatus)
async def get_status() -> OllamaRuntimeStatus:
    data = await get_manager().status()
    return OllamaRuntimeStatus(**data)


@router.post("/ollama/setup")
async def setup_ollama() -> StreamingResponse:
    """Download Ollama binary + start the daemon. Returns SSE progress."""
    mgr = get_manager()

    async def stream():
        # Phase 1: download binary (skip if already present).
        if not mgr.is_binary_installed:
            async for progress in mgr.download_binary():
                yield f"data: {json.dumps(progress)}\n\n"
                if progress.get("status") == "error":
                    return
        else:
            yield f"data: {json.dumps({'status': 'binary_exists'})}\n\n"

        # Phase 2: start the daemon.
        yield f"data: {json.dumps({'status': 'starting'})}\n\n"
        try:
            base_url = await mgr.start()
            yield (
                "data: "
                + json.dumps({"status": "ready", "base_url": base_url})
                + "\n\n"
            )
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'status': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/ollama/start")
async def start_ollama() -> dict[str, Any]:
    mgr = get_manager()
    if not mgr.is_binary_installed:
        raise HTTPException(
            status_code=400,
            detail="Ollama binary not installed — run setup first",
        )
    try:
        base_url = await mgr.start()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to start Ollama: {exc}")
    return {"status": "running", "base_url": base_url}


@router.post("/ollama/stop")
async def stop_ollama() -> dict[str, str]:
    await get_manager().stop()
    return {"status": "stopped"}


@router.delete("/ollama/uninstall")
async def uninstall_ollama(delete_models: bool = Query(False)) -> dict[str, Any]:
    result = await get_manager().uninstall(delete_models=delete_models)
    return {"status": "uninstalled", **result}


# ── Model management endpoints ────────────────────────────────────────────


@router.get("/ollama/models")
async def list_models() -> dict[str, Any]:
    base_url = _require_running()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base_url}/api/tags")
        resp.raise_for_status()
        return resp.json()


@router.get("/ollama/models/library")
async def get_library(
    q: Optional[str] = None,
    category: Optional[str] = None,
    sort: str = "popular",  # "popular" | "name" | "provider"
    page: int = 1,
    refresh: bool = False,
) -> dict[str, Any]:
    """Browse the remote model catalog.

    Supports search, category filter, sort, and pagination for infinite scroll.
    """
    models, has_more = await fetch_library(query=q, page=page, force_refresh=refresh)

    if category and category != "all":
        models = [m for m in models if m.get("category") == category]

    if not q:
        if sort == "name":
            models.sort(key=lambda m: m.get("name", "").lower())
        elif sort == "provider":
            models.sort(
                key=lambda m: (m.get("provider", ""), m.get("name", "").lower())
            )
        else:
            models.sort(key=lambda m: m.get("pulls", 0), reverse=True)

    return {
        "categories": CATEGORIES,
        "models": models,
        "has_more": has_more,
        "page": page,
    }


@router.post("/ollama/models/pull")
async def pull_model(body: ModelPullRequest) -> StreamingResponse:
    """Pull a model from the Ollama registry. SSE progress stream."""
    base_url = _require_running()

    async def stream():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/api/pull",
                    json={"name": body.name, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield f"data: {line}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield (
                "data: "
                + json.dumps({"status": "error", "message": str(exc)})
                + "\n\n"
            )

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.delete(
    "/ollama/models/{name:path}",
    response_model=ModelDeleteResponse,
)
async def delete_model(name: str) -> ModelDeleteResponse:
    base_url = _require_running()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            "DELETE",
            f"{base_url}/api/delete",
            json={"name": name},
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    resp.raise_for_status()
    return ModelDeleteResponse(status="deleted", name=name)


@router.post("/ollama/warmup")
async def warmup_model(body: ModelWarmupRequest) -> dict[str, str]:
    """Pre-load a model into memory so the first chat request is fast."""
    base_url = _require_running()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": body.model, "prompt": "", "keep_alive": "10m"},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Warmup failed: {exc}")
    return {"status": "warm", "model": body.model}


@router.get("/ollama/models/{name:path}/info")
async def model_info(name: str) -> dict[str, Any]:
    base_url = _require_running()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{base_url}/api/show",
            json={"name": name},
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    resp.raise_for_status()
    return resp.json()
