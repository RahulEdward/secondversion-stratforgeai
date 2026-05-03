"""Triple Exponential Moving Average."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Triple Exponential Moving Average."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    e1 = s.ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    return (3 * e1 - 3 * e2 + e3).rename(f"tema_{period}")
