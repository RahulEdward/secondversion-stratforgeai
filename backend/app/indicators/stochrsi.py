"""Stochastic RSI."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .rsi import compute as rsi_compute


DESCRIPTION = "Stochastic of RSI — k/d."
PARAMS = {"period": 14, "smooth_k": 3, "smooth_d": 3, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3, column: str = "close") -> pd.DataFrame:
    r = rsi_compute(df, period=period, column=column)
    rmin = r.rolling(period).min()
    rmax = r.rolling(period).max()
    k_raw = 100 * (r - rmin) / (rmax - rmin).replace(0, np.nan)
    k = k_raw.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return pd.DataFrame({"k": k, "d": d}, index=df.index)
