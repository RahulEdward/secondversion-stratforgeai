"""Arnaud Legoux Moving Average."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Arnaud Legoux Moving Average — Gaussian-weighted."
PARAMS = {"period": 9, "sigma": 6.0, "offset": 0.85, "column": "close"}


def compute(
    df: pd.DataFrame, period: int = 9, sigma: float = 6.0, offset: float = 0.85,
    column: str = "close",
) -> pd.Series:
    """Arnaud Legoux MA."""
    s = df[column].astype(float).values
    m = offset * (period - 1)
    sd = period / sigma
    weights = np.exp(-((np.arange(period) - m) ** 2) / (2 * sd * sd))
    weights /= weights.sum()
    out = np.full_like(s, np.nan, dtype=float)
    for i in range(period - 1, len(s)):
        out[i] = np.dot(s[i - period + 1: i + 1], weights)
    return pd.Series(out, index=df.index, name=f"alma_{period}")
