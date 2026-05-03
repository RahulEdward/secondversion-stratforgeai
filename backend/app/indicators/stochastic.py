"""Stochastic Oscillator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Stochastic oscillator %K and %D."
PARAMS = {"k_period": 14, "d_period": 3}


def compute(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3
) -> pd.DataFrame:
    require(df, ["high", "low", "close"], "Stochastic")
    ll = df["low"].rolling(k_period).min()
    hh = df["high"].rolling(k_period).max()
    denom = (hh - ll).replace(0, np.nan)
    k = 100 * (df["close"] - ll) / denom
    d = k.rolling(d_period).mean()
    return pd.DataFrame({"k": k, "d": d}, index=df.index)
