"""Vortex Indicator — VI+ and VI-."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Vortex Indicator — VI+ and VI-."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    require(df, ["high", "low", "close"], "vortex")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    vm_plus = (high - low.shift()).abs()
    vm_minus = (low - high.shift()).abs()
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    tr_sum = tr.rolling(period).sum()
    vi_plus = vm_plus.rolling(period).sum() / tr_sum.replace(0, np.nan)
    vi_minus = vm_minus.rolling(period).sum() / tr_sum.replace(0, np.nan)
    return pd.DataFrame({"vi_plus": vi_plus, "vi_minus": vi_minus}, index=df.index)
