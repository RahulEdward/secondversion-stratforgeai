"""Detrended Price Oscillator."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Detrended Price Oscillator."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    """Detrended Price Oscillator."""
    s = df[column].astype(float)
    shift = int(period / 2 + 1)
    return (s - s.rolling(period).mean().shift(shift)).rename(f"dpo_{period}")
