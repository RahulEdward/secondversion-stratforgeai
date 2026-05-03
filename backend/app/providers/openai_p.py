"""OpenAI provider — GPT models via API key. Subscription sign-in lands in Phase 5."""
from __future__ import annotations

from typing import List

import httpx

from .. import secrets
from .base import ModelInfo, Provider, ProviderError

PROVIDER_NAME = "openai"
API_BASE = "https://api.openai.com/v1"

# Model IDs the UI will highlight when the /models endpoint returns the very
# long raw list — kept light so we don't bias the picker too much.
_PREFERRED_PREFIXES = ("gpt-4", "gpt-5", "o1", "o3", "o4")


class OpenAIProvider(Provider):
    name = PROVIDER_NAME
    kind = "api_key"
    label = "OpenAI"

    def has_credential(self) -> bool:
        return secrets.has_key(PROVIDER_NAME)

    async def list_models(self) -> List[ModelInfo]:
        key = secrets.get_key(PROVIDER_NAME)
        if not key:
            raise ProviderError("No OpenAI API key configured")
        headers = {"Authorization": f"Bearer {key}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{API_BASE}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"OpenAI models request failed: {exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenAI models request failed: {exc}") from exc

        models: List[ModelInfo] = []
        for entry in data.get("data", []):
            mid = entry.get("id")
            if not mid:
                continue
            # Filter noise — only chat-capable families surface in the picker.
            if not any(mid.startswith(p) for p in _PREFERRED_PREFIXES):
                continue
            models.append(ModelInfo(id=mid, label=mid))
        # Newest (lexicographically highest) first as a cheap heuristic.
        models.sort(key=lambda m: m.id, reverse=True)
        return models
