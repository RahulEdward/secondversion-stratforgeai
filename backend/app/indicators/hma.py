"""Hull Moving Average."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Hull Moving Average — fast, low-lag."
PARAMS = {"period": 16, "column": "close"}


def compute(df: pd.DataFrame, period: int = 16, column: str = "close") -> pd.Series:
    """Hull MA — WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    s = df[column].astype(float)
    half = max(1, period // 2)
    sqrt = max(1, int(np.sqrt(period)))

    def _wma(x: pd.Series, n: int) -> pd.Series:
        w = np.arange(1, n + 1, dtype=float)
        return x.rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True)

    diff = 2 * _wma(s, half) - _wma(s, period)
    return _wma(diff, sqrt).rename(f"hma_{period}")
