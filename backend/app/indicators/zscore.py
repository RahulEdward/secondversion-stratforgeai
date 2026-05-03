"""Rolling Z-Score."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Rolling z-score (std deviations from mean)."
PARAMS = {"period": 20, "column": "close"}


def compute(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    return ((s - s.rolling(period).mean()) / s.rolling(period).std()).rename(f"zscore_{period}")
