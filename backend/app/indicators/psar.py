"""Parabolic SAR — value + direction (1 long / -1 short)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._utils import require


DESCRIPTION = "Parabolic SAR with direction (1 long, -1 short)."
PARAMS = {"step": 0.02, "max_step": 0.2}


def compute(
    df: pd.DataFrame, step: float = 0.02, max_step: float = 0.2,
) -> pd.DataFrame:
    """Parabolic SAR — value + direction (1 long / -1 short)."""
    require(df, ["high", "low", "close"], "psar")
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    n = len(df)
    psar_v = np.zeros(n)
    direction = np.zeros(n, dtype=int)
    if n == 0:
        return pd.DataFrame({"psar": psar_v, "direction": direction})
    bull = True
    af = step
    ep = high[0]
    psar_v[0] = low[0]
    direction[0] = 1
    for i in range(1, n):
        prev = psar_v[i - 1]
        if bull:
            psar_v[i] = prev + af * (ep - prev)
            if low[i] < psar_v[i]:
                bull = False
                psar_v[i] = ep
                ep = low[i]
                af = step
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + step, max_step)
        else:
            psar_v[i] = prev + af * (ep - prev)
            if high[i] > psar_v[i]:
                bull = True
                psar_v[i] = ep
                ep = high[i]
                af = step
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + step, max_step)
        direction[i] = 1 if bull else -1
    return pd.DataFrame({"psar": psar_v, "direction": direction}, index=df.index)
