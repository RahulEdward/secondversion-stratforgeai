"""Anthropic provider — Claude models via API key."""
from __future__ import annotations

from typing import List

import httpx

from .. import secrets
from .base import ModelInfo, Provider, ProviderError

PROVIDER_NAME = "anthropic"
API_BASE = "https://api.anthropic.com/v1"

# Fallback catalog surfaced when the /models endpoint is unreachable or the
# deployed Anthropic SDK predates the models list route. Ordered newest-first.
_FALLBACK_MODELS: List[ModelInfo] = [
    ModelInfo(id="claude-opus-4-7", label="Claude Opus 4.7", context_window=200_000),
    ModelInfo(id="claude-sonnet-4-6", label="Claude Sonnet 4.6", context_window=200_000),
    ModelInfo(id="claude-haiku-4-5-20251001", label="Claude Haiku 4.5", context_window=200_000),
    ModelInfo(id="claude-3-5-sonnet-latest", label="Claude 3.5 Sonnet", context_window=200_000),
    ModelInfo(id="claude-3-5-haiku-latest", label="Claude 3.5 Haiku", context_window=200_000),
]


class AnthropicProvider(Provider):
    name = PROVIDER_NAME
    kind = "api_key"
    label = "Anthropic"

    def has_credential(self) -> bool:
        return secrets.has_key(PROVIDER_NAME)

    async def list_models(self) -> List[ModelInfo]:
        key = secrets.get_key(PROVIDER_NAME)
        if not key:
            raise ProviderError("No Anthropic API key configured")
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{API_BASE}/models", headers=headers)
            if resp.status_code == 404:
                # Older accounts / proxies may lack /models — serve the fallback.
                return _FALLBACK_MODELS
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Anthropic models request failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic models request failed: {exc}") from exc

        models: List[ModelInfo] = []
        for entry in data.get("data", []):
            mid = entry.get("id")
            if not mid:
                continue
            models.append(
                ModelInfo(
                    id=mid,
                    label=entry.get("display_name") or mid,
                    context_window=entry.get("context_window"),
                )
            )
        return models or _FALLBACK_MODELS
