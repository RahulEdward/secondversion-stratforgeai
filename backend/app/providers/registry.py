"""Central provider registry — single place to look up concrete providers."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import Provider, ProviderAvailability
from .chatgpt_subscription import ChatGPTSubscriptionProvider
from .claude_cli_p import ClaudeCliProvider
from .google_p import GoogleProvider
from .ollama_p import OllamaProvider, DEFAULT_BASE_URL

_PROVIDERS: Dict[str, Provider] = {
    ChatGPTSubscriptionProvider.name: ChatGPTSubscriptionProvider(),
    ClaudeCliProvider.name: ClaudeCliProvider(),
    GoogleProvider.name: GoogleProvider(),
    OllamaProvider.name: OllamaProvider(),
}

PROVIDER_NAMES: List[str] = list(_PROVIDERS.keys())


def get_provider(name: str) -> Optional[Provider]:
    return _PROVIDERS.get(name)


async def provider_info(name: str) -> Optional[ProviderAvailability]:
    provider = _PROVIDERS.get(name)
    if provider is None:
        return None
    avail = ProviderAvailability(
        name=provider.name,
        kind=provider.kind,
        label=provider.label,
        has_credential=provider.has_credential(),
    )
    if isinstance(provider, OllamaProvider):
        # Ollama surfaces base URL + reachability so the Settings panel can
        # tell the user "daemon not running" without making them click models.
        avail.extra["base_url"] = provider.base_url()
        avail.extra["default_base_url"] = DEFAULT_BASE_URL
        try:
            avail.reachable = await provider.reachable()
        except Exception as exc:  # defensive — never let a ping break settings load
            avail.reachable = False
            avail.error = str(exc)
    if isinstance(provider, ChatGPTSubscriptionProvider):
        avail.reachable = provider.has_credential()
        email = provider.account_email()
        if email:
            avail.extra["email"] = email
    if isinstance(provider, ClaudeCliProvider):
        avail.reachable = provider.has_credential()
        avail.extra["cli_installed"] = provider.cli_installed()
    return avail
