"""Supertrend indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require
from .atr import compute as atr_compute


DESCRIPTION = "Supertrend line + direction (1 bullish / -1 bearish)."
PARAMS = {"period": 10, "multiplier": 3.0}


def compute(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    require(df, ["high", "low", "close"], "Supertrend")
    atr_series = atr_compute(df, period=period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + multiplier * atr_series
    lower = hl2 - multiplier * atr_series

    close = df["close"].to_numpy()
    fu = upper.to_numpy(copy=True)
    fl = lower.to_numpy(copy=True)
    t = np.full_like(close, np.nan, dtype=float)
    d = np.ones_like(close, dtype=int)

    for i in range(1, len(df)):
        fu[i] = (
            min(fu[i], fu[i - 1])
            if close[i - 1] <= fu[i - 1]
            else fu[i]
        )
        fl[i] = (
            max(fl[i], fl[i - 1])
            if close[i - 1] >= fl[i - 1]
            else fl[i]
        )
        prev_t = t[i - 1]
        if np.isnan(prev_t):
            t[i] = fl[i]
            d[i] = 1
        elif prev_t == fu[i - 1] and close[i] <= fu[i]:
            t[i] = fu[i]
            d[i] = -1
        elif prev_t == fu[i - 1] and close[i] > fu[i]:
            t[i] = fl[i]
            d[i] = 1
        elif prev_t == fl[i - 1] and close[i] >= fl[i]:
            t[i] = fl[i]
            d[i] = 1
        elif prev_t == fl[i - 1] and close[i] < fl[i]:
            t[i] = fu[i]
            d[i] = -1

    trend = pd.Series(t, index=df.index)
    direction = pd.Series(d, index=df.index)
    return pd.DataFrame(
        {"supertrend": trend, "direction": direction}, index=df.index
    )
