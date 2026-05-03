"""Relative Strength Index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import ewm_alpha, require


DESCRIPTION = "Relative Strength Index (0-100)."
PARAMS = {"period": 14, "column": "close"}


def compute(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
    require(df, [column], "RSI")
    delta = df[column].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = ewm_alpha(gain, period)
    avg_loss = ewm_alpha(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.rename(f"rsi_{period}")
