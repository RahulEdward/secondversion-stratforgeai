"""Ollama provider — local LLMs. Credential = base URL (no API key)."""
from __future__ import annotations

from typing import List

import httpx

from .. import secrets
from .base import ModelInfo, Provider, ProviderError

PROVIDER_NAME = "ollama"
DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(Provider):
    name = PROVIDER_NAME
    kind = "local"
    label = "Ollama"

    def base_url(self) -> str:
        stored = secrets.get_key(PROVIDER_NAME)
        return (stored or DEFAULT_BASE_URL).rstrip("/")

    def has_credential(self) -> bool:
        # Local provider is "configured" as long as we know a base URL — we
        # always have a default, so effectively always True.
        return True

    async def reachable(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url()}/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> List[ModelInfo]:
        url = f"{self.base_url()}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama unreachable at {self.base_url()}: {exc}"
            ) from exc

        models: List[ModelInfo] = []
        for entry in data.get("models", []):
            mid = entry.get("name") or entry.get("model")
            if not mid:
                continue
            details = entry.get("details") or {}
            label_parts = [mid]
            if details.get("parameter_size"):
                label_parts.append(details["parameter_size"])
            models.append(
                ModelInfo(
                    id=mid,
                    label=" · ".join(label_parts),
                    description=details.get("family"),
                )
            )
        return models
