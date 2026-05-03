"""T3 (Tilson) Moving Average."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "T3 Tilson moving average — smoothed and responsive."
PARAMS = {"period": 5, "vfactor": 0.7, "column": "close"}


def compute(df: pd.DataFrame, period: int = 5, vfactor: float = 0.7, column: str = "close") -> pd.Series:
    """T3 (Tilson) MA."""
    s = df[column].astype(float)
    e1 = s.ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    e4 = e3.ewm(span=period, adjust=False).mean()
    e5 = e4.ewm(span=period, adjust=False).mean()
    e6 = e5.ewm(span=period, adjust=False).mean()
    c1 = -vfactor ** 3
    c2 = 3 * vfactor ** 2 + 3 * vfactor ** 3
    c3 = -6 * vfactor ** 2 - 3 * vfactor - 3 * vfactor ** 3
    c4 = 1 + 3 * vfactor + vfactor ** 3 + 3 * vfactor ** 2
    return (c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3).rename(f"t3_{period}")
