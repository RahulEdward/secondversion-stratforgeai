"""Ultimate Oscillator."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Larry Williams' Ultimate Oscillator (0-100)."
PARAMS = {"p1": 7, "p2": 14, "p3": 28}


def compute(df: pd.DataFrame, p1: int = 7, p2: int = 14, p3: int = 28) -> pd.Series:
    require(df, ["high", "low", "close"], "ultimate_oscillator")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift()
    bp = close - pd.concat([low, prev_close], axis=1).min(axis=1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    avg = lambda n: bp.rolling(n).sum() / tr.rolling(n).sum()
    return (100 * (4 * avg(p1) + 2 * avg(p2) + avg(p3)) / 7).rename("ultosc")
