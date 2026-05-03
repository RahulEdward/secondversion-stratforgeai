"""True Range."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Single-bar True Range."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["high", "low", "close"], "true_range")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    pc = df["close"].astype(float).shift()
    return pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1).rename("tr")
