"""Negative Volume Index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Negative Volume Index — index of smart-money days."
PARAMS = {}


def compute(df: pd.DataFrame) -> pd.Series:
    require(df, ["close", "volume"], "nvi")
    pct = df["close"].astype(float).pct_change().fillna(0.0)
    vol_down = df["volume"].astype(float).diff() < 0
    out = np.full(len(df), 1000.0)
    for i in range(1, len(df)):
        out[i] = out[i - 1] * (1 + pct.iloc[i]) if vol_down.iloc[i] else out[i - 1]
    return pd.Series(out, index=df.index, name="nvi")
