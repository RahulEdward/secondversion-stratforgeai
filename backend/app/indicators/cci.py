"""Commodity Channel Index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Commodity Channel Index."
PARAMS = {"period": 20}


def compute(df: pd.DataFrame, period: int = 20) -> pd.Series:
    require(df, ["high", "low", "close"], "CCI")
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(period).mean()
    mean_dev = tp.rolling(period).apply(
        lambda x: np.mean(np.abs(x - x.mean())), raw=True
    )
    denom = (0.015 * mean_dev).replace(0, np.nan)
    return ((tp - sma_tp) / denom).rename(f"cci_{period}")
