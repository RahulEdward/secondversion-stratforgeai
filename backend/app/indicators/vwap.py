"""Volume-Weighted Average Price."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Cumulative Volume-Weighted Average Price."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["high", "low", "close", "volume"], "VWAP")
    tp = (df["high"] + df["low"] + df["close"]) / 3
    num = (tp * df["volume"]).cumsum()
    den = df["volume"].cumsum().replace(0, np.nan)
    return (num / den).rename("vwap")
