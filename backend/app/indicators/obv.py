"""On Balance Volume."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "On Balance Volume cumulative series."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["close", "volume"], "OBV")
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum().rename("obv")
