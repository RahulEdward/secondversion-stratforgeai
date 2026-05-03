"""Money Flow Index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Money Flow Index — volume-weighted RSI (0-100)."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index."""
    require(df, ["high", "low", "close", "volume"], "mfi")
    tp = (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3
    mf = tp * df["volume"].astype(float)
    pos = mf.where(tp > tp.shift(), 0.0).rolling(period).sum()
    neg = mf.where(tp < tp.shift(), 0.0).rolling(period).sum()
    ratio = pos / neg.replace(0, np.nan)
    return (100 - 100 / (1 + ratio)).rename(f"mfi_{period}")
