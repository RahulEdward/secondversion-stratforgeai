"""Midpoint — (highest + lowest)/2 of column over period."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "(highest + lowest)/2 of column over period."
PARAMS = {"period": 14, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    return ((s.rolling(period).max() + s.rolling(period).min()) / 2).rename(f"midpoint_{period}")
