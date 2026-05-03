"""Thin wrapper around OS keychain (Windows Credential Manager / macOS Keychain / Linux Secret Service).

Provides a namespaced get/set/delete/has API for provider API keys. All Phase 4
provider implementations read credentials through this module — they never
touch `keyring` directly.

Falls back to an encrypted-free JSON file at `~/StratForge/secrets.fallback.json`
when no keyring backend is available (e.g. minimal CI images). This is a
usability net, not a security feature — a real keyring is strongly preferred.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import keyring
from keyring.errors import KeyringError, NoKeyringError

from .paths import APP_ROOT, ensure_app_dirs

logger = logging.getLogger(__name__)

SERVICE_NAME = "stratforge-ai"
_FALLBACK_FILE = APP_ROOT / "secrets.fallback.json"


def _fallback_load() -> dict[str, str]:
    if not _FALLBACK_FILE.exists():
        return {}
    try:
        return json.loads(_FALLBACK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fallback_save(data: dict[str, str]) -> None:
    ensure_app_dirs()
    _FALLBACK_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _use_fallback() -> bool:
    try:
        backend = keyring.get_keyring()
        # `fail.Keyring` is the "no real backend" sentinel keyring ships with.
        return backend.__class__.__name__.lower().startswith("fail")
    except Exception:
        return True


def set_key(provider: str, value: str) -> None:
    """Store the provider's API key. Silently overwrites existing value."""
    if _use_fallback():
        data = _fallback_load()
        data[provider] = value
        _fallback_save(data)
        return
    try:
        keyring.set_password(SERVICE_NAME, provider, value)
    except (KeyringError, NoKeyringError) as exc:
        logger.warning("keyring set failed for %s: %s — using fallback", provider, exc)
        data = _fallback_load()
        data[provider] = value
        _fallback_save(data)


def get_key(provider: str) -> Optional[str]:
    if _use_fallback():
        return _fallback_load().get(provider)
    try:
        return keyring.get_password(SERVICE_NAME, provider)
    except (KeyringError, NoKeyringError) as exc:
        logger.warning("keyring get failed for %s: %s — using fallback", provider, exc)
        return _fallback_load().get(provider)


def delete_key(provider: str) -> bool:
    """Returns True if a key was removed, False if nothing was stored."""
    existed = get_key(provider) is not None
    if not existed:
        return False
    if _use_fallback():
        data = _fallback_load()
        data.pop(provider, None)
        _fallback_save(data)
        return True
    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except (KeyringError, NoKeyringError) as exc:
        logger.warning("keyring delete failed for %s: %s", provider, exc)
    # Also clear from fallback in case the backend flipped between calls.
    data = _fallback_load()
    if provider in data:
        data.pop(provider, None)
        _fallback_save(data)
    return True


def has_key(provider: str) -> bool:
    return get_key(provider) is not None
