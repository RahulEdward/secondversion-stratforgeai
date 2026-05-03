"""Keltner Channel — EMA-centred ATR bands."""

from __future__ import annotations

import pandas as pd

from ._utils import require
from .ema import compute as ema_compute
from .atr import compute as atr_compute


DESCRIPTION = "Keltner Channel — EMA-centred ATR bands."
PARAMS = {"period": 20, "multiplier": 2.0, "atr_period": 10}


def compute(
    df: pd.DataFrame, period: int = 20, multiplier: float = 2.0, atr_period: int = 10,
) -> pd.DataFrame:
    require(df, ["high", "low", "close"], "keltner")
    mid = ema_compute(df, period=period)
    a = atr_compute(df, period=atr_period)
    return pd.DataFrame({"upper": mid + multiplier * a, "middle": mid, "lower": mid - multiplier * a}, index=df.index)
