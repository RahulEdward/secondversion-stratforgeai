"""Provider interface shared by every AI backend.

Phase 4 uses only `list_models()` and the availability/credential bits.
`stream_chat()` is defined here so Phase 6 can fan out through the same
interface without re-touching the UI or the settings layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

ProviderKind = Literal["api_key", "local", "subscription"]


@dataclass
class ModelInfo:
    id: str
    label: str
    context_window: Optional[int] = None
    description: Optional[str] = None


@dataclass
class ProviderAvailability:
    """Runtime status surfaced to the Settings UI."""

    name: str
    kind: ProviderKind
    label: str
    has_credential: bool
    reachable: Optional[bool] = None  # None = not yet checked; True/False after ping
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised when a provider cannot satisfy a request (missing key, network, etc)."""


class Provider:
    """Abstract base. Implementations live in the sibling modules."""

    name: str
    kind: ProviderKind
    label: str

    def has_credential(self) -> bool:
        raise NotImplementedError

    async def list_models(self) -> List[ModelInfo]:
        raise NotImplementedError

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        system: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:  # pragma: no cover — Phase 6
        raise NotImplementedError
        # Unreachable `yield` keeps the async-iterator type.
        yield {}
