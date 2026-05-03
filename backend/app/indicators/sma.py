"""Simple Moving Average."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Simple Moving Average of a column."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    require(df, [column], "SMA")
    return df[column].rolling(window=period, min_periods=period).mean().rename(f"sma_{period}")
