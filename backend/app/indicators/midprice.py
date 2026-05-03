"""Mid Price — (rolling max high + rolling min low)/2."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "(rolling max high + rolling min low)/2."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.Series:
    require(df, ["high", "low"], "midprice")
    return (
        (df["high"].astype(float).rolling(period).max()
         + df["low"].astype(float).rolling(period).min()) / 2
    ).rename(f"midprice_{period}")
