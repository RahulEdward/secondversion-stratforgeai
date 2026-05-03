"""Rolling Correlation."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Rolling Pearson correlation between two columns."
PARAMS = {"period": 30, "col_a": "close", "col_b": "volume"}


def compute(df: pd.DataFrame, period: int = 30, col_a: str = "close", col_b: str = "volume") -> pd.Series:
    a = df[col_a].astype(float)
    b = df[col_b].astype(float)
    return a.rolling(period).corr(b).rename(f"corr_{col_a}_{col_b}_{period}")
