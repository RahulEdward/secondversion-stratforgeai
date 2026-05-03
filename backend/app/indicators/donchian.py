"""Donchian Channels — upper, middle, lower bands over N-period high/low range."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Donchian Channel — upper/middle/lower."
PARAMS = {"period": 20}


def compute(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    require(df, ["high", "low"], "donchian")
    upper = df["high"].astype(float).rolling(period).max()
    lower = df["low"].astype(float).rolling(period).min()
    middle = (upper + lower) / 2
    return pd.DataFrame({"upper": upper, "middle": middle, "lower": lower}, index=df.index)
