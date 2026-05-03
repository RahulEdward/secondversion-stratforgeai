"""Balance of Power."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Balance of Power (close-open / high-low)."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["open", "high", "low", "close"], "bop")
    return ((df["close"] - df["open"]) / (df["high"] - df["low"]).replace(0, np.nan)).rename("bop")
