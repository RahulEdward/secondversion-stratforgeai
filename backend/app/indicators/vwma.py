"""Volume-Weighted Moving Average."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Volume-Weighted Moving Average."
PARAMS = {"period": 20}


def compute(df: pd.DataFrame, period: int = 20) -> pd.Series:
    require(df, ["close", "volume"], "vwma")
    pv = (df["close"].astype(float) * df["volume"].astype(float)).rolling(period).sum()
    v = df["volume"].astype(float).rolling(period).sum()
    return (pv / v).rename(f"vwma_{period}")
