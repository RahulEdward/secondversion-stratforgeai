"""Rolling Standard Deviation."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Rolling standard deviation of column."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    return df[column].astype(float).rolling(period).std().rename(f"stddev_{period}")
