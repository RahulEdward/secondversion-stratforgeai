"""Ulcer Index — drawdown-weighted volatility."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Ulcer Index — drawdown-weighted volatility."
PARAMS = {"period": 14, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    rmax = s.rolling(period).max()
    pct_dd = 100 * (s - rmax) / rmax
    return np.sqrt((pct_dd ** 2).rolling(period).mean()).rename(f"ulcer_{period}")
