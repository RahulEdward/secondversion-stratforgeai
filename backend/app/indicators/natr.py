"""Normalised ATR — ATR as percent of close."""

from __future__ import annotations

import pandas as pd

from ._utils import require
from .atr import compute as atr_compute


DESCRIPTION = "Normalised ATR — ATR as percent of close."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    require(df, ["close"], "natr")
    a = atr_compute(df, period=period)
    return (100 * a / df["close"].astype(float)).rename(f"natr_{period}")
