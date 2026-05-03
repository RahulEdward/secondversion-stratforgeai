"""Bollinger Bands."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Bollinger Bands — upper, middle, lower."
PARAMS = {"period": 20, "std": 2.0, "column": "close"}


def compute(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
    column: str = "close",
) -> pd.DataFrame:
    require(df, [column], "Bollinger Bands")
    mid = df[column].rolling(period).mean()
    sd = df[column].rolling(period).std(ddof=0)
    upper = mid + std * sd
    lower = mid - std * sd
    return pd.DataFrame(
        {"upper": upper, "middle": mid, "lower": lower}, index=df.index
    )
