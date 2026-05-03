"""Mass Index — reversal warning oscillator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Mass Index — reversal warning oscillator."
PARAMS = {"period": 25, "ema_period": 9}


def compute(df: pd.DataFrame, period: int = 25, ema_period: int = 9) -> pd.Series:
    require(df, ["high", "low"], "mass_index")
    rng = df["high"].astype(float) - df["low"].astype(float)
    e1 = rng.ewm(span=ema_period, adjust=False).mean()
    e2 = e1.ewm(span=ema_period, adjust=False).mean()
    ratio = e1 / e2.replace(0, np.nan)
    return ratio.rolling(period).sum().rename(f"mass_{period}")
