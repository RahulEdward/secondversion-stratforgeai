"""Bias."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Bias — pct deviation of close from its SMA."
PARAMS = {"period": 26, "column": "close"}


def compute(df: pd.DataFrame, period: int = 26, column: str = "close") -> pd.Series:
    s = df[column].astype(float)
    return (100 * (s - s.rolling(period).mean()) / s.rolling(period).mean()).rename(f"bias_{period}")
