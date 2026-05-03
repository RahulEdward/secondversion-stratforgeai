"""Google provider — Gemini models via Generative Language API key."""
from __future__ import annotations

from typing import List

import httpx

from .. import secrets
from .base import ModelInfo, Provider, ProviderError

PROVIDER_NAME = "google"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(Provider):
    name = PROVIDER_NAME
    kind = "api_key"
    label = "Google"

    def has_credential(self) -> bool:
        return secrets.has_key(PROVIDER_NAME)

    async def list_models(self) -> List[ModelInfo]:
        key = secrets.get_key(PROVIDER_NAME)
        if not key:
            raise ProviderError("No Google API key configured")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{API_BASE}/models",
                    params={"key": key},
                )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Google models request failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Google models request failed: {exc}") from exc

        models: List[ModelInfo] = []
        for entry in data.get("models", []):
            name = entry.get("name", "")  # "models/gemini-1.5-pro"
            if not name:
                continue
            mid = name.split("/", 1)[-1]
            supported = entry.get("supportedGenerationMethods") or []
            if "generateContent" not in supported:
                continue
            models.append(
                ModelInfo(
                    id=mid,
                    label=entry.get("displayName") or mid,
                    context_window=entry.get("inputTokenLimit"),
                    description=entry.get("description"),
                )
            )
        models.sort(key=lambda m: m.id, reverse=True)
        return models
