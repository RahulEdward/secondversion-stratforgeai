"""Chande Momentum Oscillator."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "Chande Momentum Oscillator (-100 to 100)."
PARAMS = {"period": 14, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    s = df[column].astype(float).diff()
    up = s.where(s > 0, 0.0).rolling(period).sum()
    dn = (-s.where(s < 0, 0.0)).rolling(period).sum()
    return (100 * (up - dn) / (up + dn).replace(0, np.nan)).rename(f"cmo_{period}")
