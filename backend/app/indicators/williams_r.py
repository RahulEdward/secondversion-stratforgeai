"""Williams %R momentum oscillator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Williams %R momentum oscillator (-100 to 0)."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    require(df, ["high", "low", "close"], "Williams %R")
    hh = df["high"].rolling(period).max()
    ll = df["low"].rolling(period).min()
    denom = (hh - ll).replace(0, np.nan)
    return (-100 * (hh - df["close"]) / denom).rename(f"wr_{period}")
