"""Pivot Points (Standard)."""

from __future__ import annotations

import pandas as pd

from ._utils import require


DESCRIPTION = "Standard Pivot Points (P, R1, S1, R2, S2, R3, S3)."
PARAMS = {"period": 14}


def compute(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Standard Pivot Points based on rolling window highs and lows."""
    require(df, ["high", "low", "close"], "pivot_points")

    # Typically pivot points use the previous day's data, but to make it 
    # continuous and compatible with our indicators interface, we'll use a 
    # rolling window or previous period shifted values.
    # We will use the rolling high, low, and close shifted by 1 to get previous period's HLC.
    prev_high = df["high"].rolling(period).max().shift(1)
    prev_low = df["low"].rolling(period).min().shift(1)
    prev_close = df["close"].shift(1)

    p = (prev_high + prev_low + prev_close) / 3
    r1 = (p * 2) - prev_low
    s1 = (p * 2) - prev_high
    r2 = p + (prev_high - prev_low)
    s2 = p - (prev_high - prev_low)
    r3 = prev_high + 2 * (p - prev_low)
    s3 = prev_low - 2 * (prev_high - p)

    return pd.DataFrame(
        {
            "p": p,
            "r1": r1,
            "s1": s1,
            "r2": r2,
            "s2": s2,
            "r3": r3,
            "s3": s3,
        },
        index=df.index,
    )
