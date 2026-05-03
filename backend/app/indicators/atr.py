"""Average True Range."""

from __future__ import annotations

import pandas as pd

from ._utils import ewm_alpha, require


DESCRIPTION = "Average True Range volatility measure."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    require(df, ["high", "low", "close"], "ATR")
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return ewm_alpha(tr, period).rename(f"atr_{period}")
