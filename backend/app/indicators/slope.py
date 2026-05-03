"""Slope of Linear Regression."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Slope of rolling linear regression."
PARAMS = {"period": 14, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    s = df[column].astype(float)

    def _slope(x: np.ndarray) -> float:
        n = len(x)
        if n < 2:
            return float("nan")
        idx = np.arange(n)
        return float(np.polyfit(idx, x, 1)[0])

    return s.rolling(period).apply(_slope, raw=True).rename(f"slope_{period}")
