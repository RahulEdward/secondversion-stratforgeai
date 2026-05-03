"""Kaufman Adaptive Moving Average."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Kaufman Adaptive Moving Average."
PARAMS = {"period": 10, "fast": 2, "slow": 30, "column": "close"}


def compute(
    df: pd.DataFrame, period: int = 10, fast: int = 2, slow: int = 30,
    column: str = "close",
) -> pd.Series:
    """Kaufman Adaptive MA."""
    s = df[column].astype(float)
    change = s.diff(period).abs()
    volatility = s.diff().abs().rolling(period).sum()
    er = (change / volatility).fillna(0.0)
    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    out = s.copy()
    out.iloc[: period] = s.iloc[: period].mean()
    for i in range(period, len(s)):
        out.iloc[i] = out.iloc[i - 1] + sc.iloc[i] * (s.iloc[i] - out.iloc[i - 1])
    return out.rename(f"kama_{period}")
