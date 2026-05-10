"""Loader registry — StratForge-only edition.

StratForge AI uses its own uploaded-parquet datasets exclusively. External
loaders (tushare / okx / yfinance / akshare / ccxt / futu) are no longer
registered — they required network access and API tokens that the desktop
app doesn't ship.

Every fallback chain now points to a single loader: ``stratforge``.
"""

from __future__ import annotations

import logging
from typing import Any, Type

from app.backtest_engine.loaders.base import NoAvailableSourceError

logger = logging.getLogger(__name__)

# ─── Global registry ────────────────────────────────────────────────────

LOADER_REGISTRY: dict[str, Type[Any]] = {}

_registered = False


def register(cls: Type[Any]) -> Type[Any]:
    """Class decorator: register a loader into the global registry."""
    LOADER_REGISTRY[cls.name] = cls
    return cls


def _ensure_registered() -> None:
    """Import the StratForge loader module so ``@register`` fires.

    Safe to call multiple times — only runs once.
    """
    global _registered
    if _registered:
        return
    _registered = True

    import importlib
    try:
        importlib.import_module("app.backtest_engine.loaders.stratforge_loader")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to register StratForge loader: %s", exc)


# ─── Fallback chains — all point to stratforge ──────────────────────────

FALLBACK_CHAINS: dict[str, list[str]] = {
    "a_share":   ["stratforge"],
    "us_equity": ["stratforge"],
    "hk_equity": ["stratforge"],
    "crypto":    ["stratforge"],
    "futures":   ["stratforge"],
    "fund":      ["stratforge"],
    "macro":     ["stratforge"],
    "forex":     ["stratforge"],
}


def resolve_loader(market: str) -> Any:
    """Return a StratForge loader instance for any market.

    Raises:
        NoAvailableSourceError: If somehow the StratForge loader isn't
        registered (should never happen — the module always imports).
    """
    _ensure_registered()
    if "stratforge" not in LOADER_REGISTRY:
        raise NoAvailableSourceError(
            "StratForge loader not registered. Check that "
            "backend/app/backtest_engine/loaders/stratforge_loader.py exists."
        )
    return LOADER_REGISTRY["stratforge"]()


def get_loader_cls_with_fallback(source: str) -> Type[Any]:
    """Return a loader class by name, always falling back to ``stratforge``.

    This keeps legacy code paths (e.g. ``source: "auto"``) working: any
    unknown / unsupported source silently degrades to StratForge instead
    of erroring out.
    """
    _ensure_registered()
    if source in LOADER_REGISTRY:
        return LOADER_REGISTRY[source]
    # Fallback — StratForge handles every market
    if "stratforge" in LOADER_REGISTRY:
        return LOADER_REGISTRY["stratforge"]
    raise NoAvailableSourceError(
        f"Unknown data source '{source}' and StratForge loader unavailable."
    )
