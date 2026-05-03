"""Typical Price."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "(high + low + close) / 3."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["high", "low", "close"], "typical_price")
    return ((df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3).rename("typical")
