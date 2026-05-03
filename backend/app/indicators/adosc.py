"""Chaikin A/D Oscillator."""

from __future__ import annotations

import pandas as pd

from .ad import compute as ad_compute


DESCRIPTION = "Chaikin A/D Oscillator (fast - slow EMA of A/D)."
PARAMS = {"fast": 3, "slow": 10}


def compute(df: pd.DataFrame, fast: int = 3, slow: int = 10) -> pd.Series:
    a = ad_compute(df)
    return (a.ewm(span=fast, adjust=False).mean() - a.ewm(span=slow, adjust=False).mean()).rename("adosc")
