"""Accumulation/Distribution Line."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Accumulation/Distribution Line."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    """Accumulation/Distribution Line."""
    require(df, ["high", "low", "close", "volume"], "ad")
    rng = df["high"].astype(float) - df["low"].astype(float)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng.replace(0, np.nan)
    return (mfm * df["volume"].astype(float)).cumsum().rename("ad")
