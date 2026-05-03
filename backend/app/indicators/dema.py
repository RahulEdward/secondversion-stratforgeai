"""Double Exponential Moving Average."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Double Exponential Moving Average."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    e1 = s.ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    return (2 * e1 - e2).rename(f"dema_{period}")
