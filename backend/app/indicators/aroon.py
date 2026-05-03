"""Aroon Indicator — up/down/oscillator."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Aroon up/down/oscillator (0-100)."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    require(df, ["high", "low"], "aroon")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    up = high.rolling(period + 1).apply(lambda x: 100 * (period - (period - x.argmax())) / period, raw=True)
    dn = low.rolling(period + 1).apply(lambda x: 100 * (period - (period - x.argmin())) / period, raw=True)
    return pd.DataFrame({"aroon_up": up, "aroon_down": dn, "aroon_osc": up - dn}, index=df.index)
