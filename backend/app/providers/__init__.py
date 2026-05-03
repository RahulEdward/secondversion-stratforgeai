"""AI provider abstractions and implementations.

Phase 4 exposes model listing + credential management for four providers:
Anthropic, OpenAI, Google, and Ollama. Streaming chat will be wired in Phase 6
through the same `Provider.stream_chat` contract defined in `base.py`.
"""
from .base import ModelInfo, Provider, ProviderAvailability, ProviderKind
from .registry import PROVIDER_NAMES, get_provider, provider_info

__all__ = [
    "ModelInfo",
    "Provider",
    "ProviderAvailability",
    "ProviderKind",
    "PROVIDER_NAMES",
    "get_provider",
    "provider_info",
]
