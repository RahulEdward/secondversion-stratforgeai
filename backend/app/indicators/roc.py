"""Rate of Change."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Rate of Change (percent) over a lookback period."
PARAMS = {"period": 10, "column": "close"}


def compute(df: pd.DataFrame, period: int = 10, column: str = "close") -> pd.Series:
    require(df, [column], "ROC")
    return (
        (df[column] / df[column].shift(period) - 1.0) * 100
    ).rename(f"roc_{period}")
