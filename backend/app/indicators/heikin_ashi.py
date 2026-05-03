"""Heikin Ashi candles."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Heikin Ashi open, high, low, close."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.DataFrame:
    require(df, ["open", "high", "low", "close"], "heikin_ashi")
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4

    # HA Open needs to be calculated sequentially
    ha_open = np.zeros_like(df["open"].values)
    ha_open[0] = (df["open"].iloc[0] + df["close"].iloc[0]) / 2

    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i - 1] + ha_close.iloc[i - 1]) / 2

    ha_open_series = pd.Series(ha_open, index=df.index)

    ha_high = pd.concat([df["high"], ha_open_series, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open_series, ha_close], axis=1).min(axis=1)

    return pd.DataFrame(
        {
            "ha_open": ha_open_series,
            "ha_high": ha_high,
            "ha_low": ha_low,
            "ha_close": ha_close,
        },
        index=df.index,
    )
