"""Ease of Movement."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Ease of Movement."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Ease of Movement."""
    require(df, ["high", "low", "volume"], "eom")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    distance = ((high + low) / 2) - ((high.shift() + low.shift()) / 2)
    box = (df["volume"].astype(float) / 100_000_000) / (high - low).replace(0, np.nan)
    return (distance / box).rolling(period).mean().rename(f"eom_{period}")
