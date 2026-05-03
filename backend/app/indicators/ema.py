"""Exponential Moving Average."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Exponential Moving Average of a column."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    require(df, [column], "EMA")
    return (
        df[column]
        .ewm(span=period, adjust=False, min_periods=period)
        .mean()
        .rename(f"ema_{period}")
    )
