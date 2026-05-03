"""Linear Regression."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Last value of rolling linear regression line."
PARAMS = {"period": 14, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    s = df[column].astype(float)

    def _last(x: np.ndarray) -> float:
        n = len(x)
        if n < 2:
            return float("nan")
        idx = np.arange(n)
        m, b = np.polyfit(idx, x, 1)
        return m * (n - 1) + b

    return s.rolling(period).apply(_last, raw=True).rename(f"linreg_{period}")
