"""Rolling Beta."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Rolling beta between two columns."
PARAMS = {"period": 30, "col_a": "close", "col_b": "volume"}


def compute(df: pd.DataFrame, period: int = 30, col_a: str = "close", col_b: str = "volume") -> pd.Series:
    a = df[col_a].astype(float).pct_change()
    b = df[col_b].astype(float).pct_change()
    cov = a.rolling(period).cov(b)
    var_b = b.rolling(period).var()
    return (cov / var_b.replace(0, np.nan)).rename(f"beta_{col_a}_{col_b}_{period}")
