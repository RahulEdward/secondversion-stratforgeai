"""TRIX — Triple-smoothed EMA percent change."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Triple-smoothed EMA percent change (basis points)."
PARAMS = {"period": 18, "column": "close"}


def compute(df: pd.DataFrame, period: int = 18, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    e1 = s.ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    return (e3.pct_change() * 10000).rename(f"trix_{period}")
