"""True Strength Index."""

from __future__ import annotations

import numpy as np
import pandas as pd


DESCRIPTION = "True Strength Index with signal."
PARAMS = {"long": 25, "short": 13, "signal": 13, "column": "close"}


def compute(df: pd.DataFrame, long: int = 25, short: int = 13, signal: int = 13, column: str = "close") -> pd.DataFrame:
    s = df[column].astype(float)
    m = s.diff()
    abs_m = m.abs()
    ema1 = m.ewm(span=long, adjust=False).mean().ewm(span=short, adjust=False).mean()
    ema2 = abs_m.ewm(span=long, adjust=False).mean().ewm(span=short, adjust=False).mean()
    line = 100 * ema1 / ema2.replace(0, np.nan)
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"tsi": line, "signal": sig}, index=df.index)
