"""Indicator registry and dynamic dispatch.

This module replaces the old monolithic indicators file. It dynamically loads
all available indicators and exposes the standard `compute` interface.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Dict

import pandas as pd

from ._utils import IndicatorError

# Central registry: name -> {"fn": compute_fn, "description": str, "params": dict}
INDICATOR_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _discover_indicators():
    """Dynamically discover and register all indicators in this package."""
    from . import _utils  # don't register utils

    for module_info in pkgutil.iter_modules(__path__):
        name = module_info.name
        if name.startswith("_"):
            continue

        module = importlib.import_module(f".{name}", __package__)
        
        if hasattr(module, "compute"):
            INDICATOR_REGISTRY[name] = {
                "fn": module.compute,
                "description": getattr(module, "DESCRIPTION", f"{name} indicator"),
                "params": getattr(module, "PARAMS", {}),
            }

_discover_indicators()


def compute(
    df: pd.DataFrame, name: str, params: Dict[str, object] | None = None
) -> pd.DataFrame:
    """Look up an indicator by name and run it with merged params. Returns a DataFrame
    (single-output indicators are wrapped into a one-column frame for uniform JSON output)."""
    if name not in INDICATOR_REGISTRY:
        raise IndicatorError(f"Unknown indicator '{name}'")
    entry = INDICATOR_REGISTRY[name]
    defaults = dict(entry["params"])
    if params:
        defaults.update(params)
    result = entry["fn"](df, **defaults)
    if isinstance(result, pd.Series):
        return result.to_frame()
    return result
