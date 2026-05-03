"""Ehlers Fisher Transform."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Ehlers Fisher Transform — fish + trigger."
PARAMS = {"period": 9}


def compute(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
    """Ehlers Fisher Transform."""
    require(df, ["high", "low"], "fisher")
    mid = (df["high"].astype(float) + df["low"].astype(float)) / 2
    rng = mid.rolling(period).max() - mid.rolling(period).min()
    norm = ((mid - mid.rolling(period).min()) / rng.replace(0, np.nan) - 0.5) * 2
    norm = norm.clip(-0.999, 0.999)
    fish = 0.5 * np.log((1 + norm) / (1 - norm))
    return pd.DataFrame({"fisher": fish, "trigger": fish.shift(1)}, index=df.index)
