"""Chaikin Money Flow."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Chaikin Money Flow (-1..1)."
PARAMS = {"period": 20}


def compute(df: pd.DataFrame, period: int = 20) -> pd.Series:
    require(df, ["high", "low", "close", "volume"], "cmf")
    rng = df["high"].astype(float) - df["low"].astype(float)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng.replace(0, np.nan)
    # `rng == 0` (doji bars where high == low) makes mfm NaN, which then
    # poisons every rolling window that contains it — even if every other
    # bar is fine. Treat those bars as zero money-flow contribution.
    mfv = (mfm.fillna(0.0)) * df["volume"].astype(float)
    vol_sum = df["volume"].astype(float).rolling(period, min_periods=1).sum()
    return (mfv.rolling(period, min_periods=1).sum()
            / vol_sum.replace(0, np.nan)).rename(f"cmf_{period}")
