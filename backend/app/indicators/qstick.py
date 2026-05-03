"""Q-Stick — average (close - open) over period."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Q-Stick — average (close - open) over period."
PARAMS = {"period": 10}


def compute(df: pd.DataFrame, period: int = 10) -> pd.Series:
    require(df, ["open", "close"], "qstick")
    return (df["close"] - df["open"]).rolling(period).mean().rename(f"qstick_{period}")
