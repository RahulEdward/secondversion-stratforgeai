"""Rolling Variance."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Rolling variance of column."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    return df[column].astype(float).rolling(period).var().rename(f"var_{period}")
