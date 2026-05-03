"""Price Volume Trend."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Price Volume Trend — cumulative pct-change × volume."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["close", "volume"], "pvt")
    return (df["close"].astype(float).pct_change().fillna(0.0) * df["volume"].astype(float)).cumsum().rename("pvt")
