"""Shared utilities for all indicator modules.

Provides common helpers (column validation, Wilder-style EMA) so every
indicator file can stay focused on its own computation logic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class IndicatorError(ValueError):
    """Raised when inputs are insufficient or invalid for an indicator."""


def require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    """Validate that *df* contains every column in *cols*."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise IndicatorError(
            f"{name} requires columns {cols}; missing: {missing}"
        )


def ewm_alpha(series: pd.Series, length: int) -> pd.Series:
    """Wilder-style EMA (alpha = 1/length), used by RSI/ATR/ADX."""
    return series.ewm(alpha=1.0 / length, adjust=False).mean()
