"""Raw Momentum — price difference over period."""

from __future__ import annotations

import pandas as pd


DESCRIPTION = "Raw price difference over period."
PARAMS = {"period": 10, "column": "close"}


def compute(df: pd.DataFrame, period: int = 10, column: str = "close") -> pd.Series:
    return (df[column].astype(float).diff(period)).rename(f"mom_{period}")
