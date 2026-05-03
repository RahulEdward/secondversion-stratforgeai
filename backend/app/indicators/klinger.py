"""Klinger Volume Oscillator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Klinger Volume Oscillator + signal."
PARAMS = {"fast": 34, "slow": 55, "signal": 13}


def compute(df: pd.DataFrame, fast: int = 34, slow: int = 55, signal: int = 13) -> pd.DataFrame:
    require(df, ["high", "low", "close", "volume"], "klinger")
    hlc = (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3
    trend = np.sign(hlc.diff().fillna(0.0))
    vf = df["volume"].astype(float) * trend
    line = vf.ewm(span=fast, adjust=False).mean() - vf.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"klinger": line, "signal": sig}, index=df.index)
