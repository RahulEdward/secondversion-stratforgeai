"""Average Directional Index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import ewm_alpha, require
from .atr import compute as atr_compute


DESCRIPTION = "Average Directional Index with +DI and -DI."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    require(df, ["high", "low", "close"], "ADX")
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )
    atr_series = atr_compute(df, period=period)
    plus_di = 100 * ewm_alpha(plus_dm, period) / atr_series.replace(0, np.nan)
    minus_di = 100 * ewm_alpha(minus_dm, period) / atr_series.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_series = ewm_alpha(dx, period)
    return pd.DataFrame(
        {
            "adx": adx_series, 
            "plus_di": plus_di, 
            "minus_di": minus_di,
            "+di": plus_di,
            "-di": minus_di
        },
        index=df.index,
    )
